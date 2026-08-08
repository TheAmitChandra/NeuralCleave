"""Tests for McpContent and McpToolDescriptor serialisation."""

from __future__ import annotations

from neuralcleave.mcp.protocol import McpCapabilities, McpContent, McpServerInfo, McpToolDescriptor


class TestMcpContent:
    def test_text_content_to_dict_has_type(self) -> None:
        content = McpContent(type="text", text="hello")
        assert content.to_dict()["type"] == "text"

    def test_text_content_to_dict_has_text(self) -> None:
        content = McpContent(type="text", text="hello world")
        assert content.to_dict()["text"] == "hello world"

    def test_empty_text_omits_text_key(self) -> None:
        content = McpContent(type="text", text="")
        d = content.to_dict()
        assert "text" not in d


class TestMcpToolDescriptor:
    def test_to_dict_has_name(self) -> None:
        desc = McpToolDescriptor(name="shell", description="Run commands.", input_schema={})
        assert desc.to_dict()["name"] == "shell"

    def test_to_dict_has_description(self) -> None:
        desc = McpToolDescriptor(name="x", description="Do X.", input_schema={})
        assert desc.to_dict()["description"] == "Do X."

    def test_to_dict_uses_input_schema_key(self) -> None:
        schema = {"type": "object", "properties": {}}
        desc = McpToolDescriptor(name="x", description="x", input_schema=schema)
        assert "inputSchema" in desc.to_dict()
        assert desc.to_dict()["inputSchema"] == schema


class TestMcpServerInfo:
    def test_default_name_is_neuralcleave(self) -> None:
        info = McpServerInfo()
        assert info.to_dict()["name"] == "neuralcleave"

    def test_default_version(self) -> None:
        info = McpServerInfo()
        assert info.to_dict()["version"] == "2.1.5"


class TestMcpCapabilities:
    def test_tools_capability_present_when_enabled(self) -> None:
        caps = McpCapabilities(tools=True)
        assert "tools" in caps.to_dict()

    def test_resources_absent_when_disabled(self) -> None:
        caps = McpCapabilities(resources=False)
        assert "resources" not in caps.to_dict()

    def test_prompts_absent_when_disabled(self) -> None:
        caps = McpCapabilities(prompts=False)
        assert "prompts" not in caps.to_dict()
