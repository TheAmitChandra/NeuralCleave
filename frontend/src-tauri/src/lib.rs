use tauri::{
  menu::{Menu, MenuItem},
  tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
  AppHandle, Manager,
};
#[cfg(desktop)]
use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState};

/// Shows the main window and gives it focus. Shared by the tray's
/// "Show" menu item and the global hotkey — both should behave
/// identically (unlike the tray icon's left-click, which toggles).
fn show_and_focus(app: &AppHandle) {
  log::info!("show_and_focus: summoning main window");
  if let Some(window) = app.get_webview_window("main") {
    let _ = window.show();
    let _ = window.set_focus();
  }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  let builder = tauri::Builder::default();

  // Global shortcuts aren't supported on mobile — see the matching
  // cfg-gated dependency in Cargo.toml.
  #[cfg(desktop)]
  let builder = builder.plugin(
    tauri_plugin_global_shortcut::Builder::new()
      .with_handler(|app, shortcut, event| {
        log::info!(
          "global-shortcut event received: {:?} state={:?}",
          shortcut,
          event.state()
        );
        if event.state() == ShortcutState::Pressed
          && shortcut.matches(Modifiers::CONTROL | Modifiers::SHIFT, Code::Space)
        {
          show_and_focus(app);
        }
      })
      .build(),
  );

  builder
    .setup(|app| {
      if cfg!(debug_assertions) {
        app.handle().plugin(
          tauri_plugin_log::Builder::default()
            .level(log::LevelFilter::Info)
            .build(),
        )?;
      }

      // ── Global hotkey: Ctrl+Shift+Space summons the window from
      // anywhere, even when minimized to the tray ────────────────────
      #[cfg(desktop)]
      {
        let summon = Shortcut::new(Some(Modifiers::CONTROL | Modifiers::SHIFT), Code::Space);
        app.global_shortcut().register(summon)?;
      }

      // ── System tray ──────────────────────────────────────────────
      // Closing the main window hides it instead of quitting — the
      // tray icon's "Quit" item (or right-click > Quit) is the only
      // way to actually exit. Left-click on the tray icon toggles the
      // window's visibility, matching the convention most tray-based
      // chat/assistant apps use.
      let show_item = MenuItem::with_id(app, "show", "Show CortexFlow-AI", true, None::<&str>)?;
      let quit_item = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
      let tray_menu = Menu::with_items(app, &[&show_item, &quit_item])?;

      TrayIconBuilder::new()
        .icon(app.default_window_icon().unwrap().clone())
        .menu(&tray_menu)
        .show_menu_on_left_click(false)
        .tooltip("CortexFlow-AI")
        .on_menu_event(|app, event| match event.id.as_ref() {
          "show" => show_and_focus(app),
          "quit" => app.exit(0),
          _ => {}
        })
        .on_tray_icon_event(|tray, event| {
          if let TrayIconEvent::Click {
            button: MouseButton::Left,
            button_state: MouseButtonState::Up,
            ..
          } = event
          {
            let app = tray.app_handle();
            if let Some(window) = app.get_webview_window("main") {
              let is_visible = window.is_visible().unwrap_or(false);
              if is_visible {
                let _ = window.hide();
              } else {
                let _ = window.show();
                let _ = window.set_focus();
              }
            }
          }
        })
        .build(app)?;

      if let Some(window) = app.get_webview_window("main") {
        let window_for_close = window.clone();
        window.on_window_event(move |event| {
          if let tauri::WindowEvent::CloseRequested { api, .. } = event {
            api.prevent_close();
            let _ = window_for_close.hide();
          }
        });
      }

      Ok(())
    })
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}
