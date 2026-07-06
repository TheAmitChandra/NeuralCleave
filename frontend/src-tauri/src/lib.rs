use std::sync::Mutex;

use tauri::{
  menu::{Menu, MenuItem},
  tray::{MouseButton, MouseButtonState, TrayIcon, TrayIconBuilder, TrayIconEvent},
  AppHandle, Manager, RunEvent, State,
};
use tauri_plugin_shell::{process::CommandChild, ShellExt};
#[cfg(desktop)]
use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState};

/// Holds the running Python backend sidecar process so we can kill it on exit.
struct BackendProcess(Mutex<Option<CommandChild>>);

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

/// Updates the tray tooltip to reflect the total unread count across all
/// channels. There's no native numeric overlay badge on a Windows tray
/// icon via Tauri's API, so the tooltip is the cross-platform-safe choice
/// — it's always available, unlike icon swapping (which would need extra
/// badged icon assets we don't have yet).
#[tauri::command]
fn set_unread_badge(app: AppHandle, count: u32) -> Result<(), String> {
  let tray: State<'_, TrayIcon> = app.state();
  let tooltip = if count == 0 {
    "CortexFlow-AI".to_string()
  } else {
    format!("CortexFlow-AI — {count} unread")
  };
  log::info!("set_unread_badge: count={count} tooltip={tooltip:?}");
  tray
    .set_tooltip(Some(&tooltip))
    .map_err(|e| e.to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  let builder = tauri::Builder::default();

  // Must be registered before any other plugin: closing the main
  // window hides it instead of quitting (see the CloseRequested
  // handler below), so the process is still alive in the tray the
  // next time the user double-clicks the .exe. Without this guard,
  // that second launch starts a second OS process, which then panics
  // in setup() below when it tries to register the global hotkey —
  // the OS rejects it because the first (still-running) instance
  // already holds it. This plugin intercepts the second launch at
  // the OS level and forwards it to the first instance instead.
  #[cfg(desktop)]
  let builder = builder.plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
    log::info!("single-instance: second launch detected, focusing existing window");
    show_and_focus(app);
  }));

  // Global shortcuts and autostart aren't supported on mobile — see
  // the matching cfg-gated dependencies in Cargo.toml.
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

  #[cfg(desktop)]
  let builder = builder.plugin(tauri_plugin_autostart::init(
    tauri_plugin_autostart::MacosLauncher::LaunchAgent,
    None,
  ));

  // Notifications are supported on mobile too, so this one isn't
  // cfg-gated like the two plugins above.
  let builder = builder.plugin(tauri_plugin_notification::init());

  // Shell plugin — required to spawn the Python backend sidecar.
  let builder = builder.plugin(tauri_plugin_shell::init());

  let app = builder
    .manage(BackendProcess(Mutex::new(None)))
    .invoke_handler(tauri::generate_handler![set_unread_badge])
    .setup(|app| {
      if cfg!(debug_assertions) {
        app.handle().plugin(
          tauri_plugin_log::Builder::default()
            .level(log::LevelFilter::Info)
            .build(),
        )?;
      }

      // ── Spawn the Python backend sidecar ─────────────────────────────
      // The binary is embedded in the installer as
      // binaries/cortexflow-backend-<target-triple>.exe; Tauri resolves
      // the platform suffix automatically.
      // In dev mode the binary may not exist yet — log the error but
      // don't abort so `npm run tauri dev` still works without running
      // bundle_backend.ps1 first.
      match app.shell().sidecar("cortexflow-backend") {
        Ok(cmd) => match cmd.spawn() {
          Ok((_rx, child)) => {
            log::info!("cortexflow-backend sidecar started");
            *app.state::<BackendProcess>().0.lock().unwrap() = Some(child);
          }
          Err(e) => log::warn!("could not spawn cortexflow-backend sidecar: {e}"),
        },
        Err(e) => log::warn!("cortexflow-backend sidecar not available: {e}"),
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

      let tray = TrayIconBuilder::new()
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
      // Stored so set_unread_badge (invoked from the frontend) can update
      // the tooltip later — TrayIconBuilder::build() only returns a handle
      // at construction time, so it needs to be kept somewhere reachable.
      app.manage(tray);

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
    .build(tauri::generate_context!())
    .expect("error while building tauri application");

  app.run(|app_handle, event| {
    if let RunEvent::Exit = event {
      // Kill the Python backend sidecar so it doesn't linger after the
      // Tauri window closes.
      if let Some(child) = app_handle
        .state::<BackendProcess>()
        .0
        .lock()
        .unwrap()
        .take()
      {
        log::info!("killing cortexflow-backend sidecar");
        let _ = child.kill();
      }
    }
  });
}
