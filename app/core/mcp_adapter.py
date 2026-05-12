import asyncio
import json
import uuid
import logging
from typing import Any, Optional
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)


@dataclass
class MCPTool:
    name: str
    description: str
    input_schema: dict
    server_name: str = ""


@dataclass
class MCPResource:
    uri: str
    name: str
    description: str
    mime_type: str = "text/plain"
    server_name: str = ""


@dataclass
class MCPServerCapabilities:
    tools: bool = False
    resources: bool = False
    prompts: bool = False


class MCPAdapter:
    def __init__(self, server_url: str = None):
        self.server_url = server_url
        self.tools: dict[str, MCPTool] = {}
        self.resources: dict[str, MCPResource] = {}
        self.capabilities = MCPServerCapabilities()
        self._client: Optional[httpx.AsyncClient] = None
        self._initialized = False
        self._request_id = 0

    async def connect(self) -> bool:
        if not self.server_url:
            logger.warning("MCP Adapter: No server URL provided")
            return False

        try:
            self._client = httpx.AsyncClient(timeout=30.0)
            initialize_result = await self._send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "orova-hermes",
                    "version": "1.0.0"
                }
            })

            if initialize_result:
                self._process_capabilities(initialize_result.get("capabilities", {}))
                self._initialized = True
                logger.info(f"MCP Adapter: Connected to {self.server_url}")

                await self._send_notification("initialized", {})
                await self._load_tools_and_resources()

            return self._initialized

        except Exception as e:
            logger.error(f"MCP Adapter: Connection failed - {e}")
            return False

    def _process_capabilities(self, capabilities: dict):
        self.capabilities.tools = capabilities.get("tools", {})
        self.capabilities.resources = capabilities.get("resources", {})
        self.capabilities.prompts = capabilities.get("prompts", {})

    async def _load_tools_and_resources(self):
        if self.capabilities.tools:
            tools_result = await self._send_request("tools/list", {})
            if tools_result and "tools" in tools_result:
                for tool in tools_result["tools"]:
                    mcp_tool = MCPTool(
                        name=tool["name"],
                        description=tool.get("description", ""),
                        input_schema=tool.get("inputSchema", {}),
                        server_name=self.server_url
                    )
                    self.tools[tool["name"]] = mcp_tool

        if self.capabilities.resources:
            resources_result = await self._send_request("resources/list", {})
            if resources_result and "resources" in resources_result:
                for resource in resources_result["resources"]:
                    mcp_resource = MCPResource(
                        uri=resource["uri"],
                        name=resource.get("name", resource["uri"]),
                        description=resource.get("description", ""),
                        mime_type=resource.get("mimeType", "text/plain"),
                        server_name=self.server_url
                    )
                    self.resources[resource["uri"]] = mcp_resource

    async def _send_request(self, method: str, params: dict) -> Optional[dict]:
        if not self._client:
            return None

        self._request_id += 1
        request_body = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params
        }

        try:
            response = await self._client.post(
                self.server_url,
                json=request_body,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            result = response.json()

            if "error" in result:
                logger.error(f"MCP JSON-RPC error: {result['error']}")
                return None

            return result.get("result")

        except httpx.HTTPError as e:
            logger.error(f"MCP HTTP error: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"MCP JSON decode error: {e}")
            return None

    async def _send_notification(self, method: str, params: dict):
        if not self._client:
            return

        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }

        try:
            await self._client.post(
                self.server_url,
                json=notification,
                headers={"Content-Type": "application/json"}
            )
        except Exception as e:
            logger.error(f"MCP notification error: {e}")

    def list_tools(self) -> list:
        return list(self.tools.values())

    def get_tool_schemas(self) -> list:
        schemas = []
        for tool in self.tools.values():
            schemas.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema
                }
            })
        return schemas

    async def call_tool(self, name: str, arguments: dict) -> Any:
        if name not in self.tools:
            raise ValueError(f"Tool '{name}' not found")

        result = await self._send_request("tools/call", {
            "name": name,
            "arguments": arguments
        })

        if result and "content" in result:
            contents = result["content"]
            if contents and len(contents) > 0:
                content = contents[0]
                if content.get("type") == "text":
                    return content.get("text")
                return content
        return result

    async def list_resources(self) -> list:
        return list(self.resources.values())

    async def read_resource(self, uri: str) -> Any:
        if uri not in self.resources:
            raise ValueError(f"Resource '{uri}' not found")

        result = await self._send_request("resources/read", {
            "uri": uri
        })

        if result and "contents" in result:
            contents = result["contents"]
            if contents and len(contents) > 0:
                content = contents[0]
                if content.get("type") == "text":
                    return content.get("text")
                elif content.get("type") == "blob":
                    return content.get("blob")
                return content
        return result

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
            self._initialized = False


class MCPRegistry:
    def __init__(self):
        self.servers: dict[str, MCPAdapter] = {}
        self._global_tools_cache: list = []
        self._cache_valid = False

    def register(self, name: str, adapter: MCPAdapter):
        self.servers[name] = adapter
        self._cache_valid = False
        logger.info(f"MCPRegistry: Registered server '{name}' at {adapter.server_url}")

    def get(self, name: str) -> Optional[MCPAdapter]:
        return self.servers.get(name)

    def unregister(self, name: str):
        if name in self.servers:
            asyncio.create_task(self.servers[name].close())
            del self.servers[name]
            self._cache_valid = False
            logger.info(f"MCPRegistry: Unregistered server '{name}'")

    def list_servers(self) -> list:
        return [
            {
                "name": name,
                "url": adapter.server_url,
                "tools_count": len(adapter.tools),
                "resources_count": len(adapter.resources),
                "connected": adapter._initialized
            }
            for name, adapter in self.servers.items()
        ]

    def list_all_tools(self) -> list:
        if self._cache_valid and self._global_tools_cache:
            return self._global_tools_cache

        all_tools = []
        for name, adapter in self.servers.items():
            if adapter._initialized:
                for tool in adapter.tools.values():
                    all_tools.append({
                        "server": name,
                        "name": tool.name,
                        "description": tool.description,
                        "input_schema": tool.input_schema
                    })

        self._global_tools_cache = all_tools
        self._cache_valid = True
        return all_tools

    def get_all_tool_schemas(self) -> list:
        schemas = []
        for name, adapter in self.servers.items():
            if adapter._initialized:
                for tool in adapter.tools.values():
                    schemas.append({
                        "type": "function",
                        "function": {
                            "name": f"{name}_{tool.name}",
                            "description": f"[{name}] {tool.description}",
                            "parameters": tool.input_schema
                        }
                    })
        return schemas

    async def call_tool(self, server_name: str, tool_name: str, arguments: dict) -> Any:
        adapter = self.get(server_name)
        if not adapter:
            raise ValueError(f"Server '{server_name}' not registered")
        return await adapter.call_tool(tool_name, arguments)

    def list_all_resources(self) -> list:
        all_resources = []
        for name, adapter in self.servers.items():
            if adapter._initialized:
                for resource in adapter.resources.values():
                    all_resources.append({
                        "server": name,
                        "uri": resource.uri,
                        "name": resource.name,
                        "description": resource.description,
                        "mime_type": resource.mime_type
                    })
        return all_resources

    async def read_resource(self, server_name: str, uri: str) -> Any:
        adapter = self.get(server_name)
        if not adapter:
            raise ValueError(f"Server '{server_name}' not registered")
        return await adapter.read_resource(uri)

    async def close_all(self):
        for adapter in self.servers.values():
            await adapter.close()
        self.servers.clear()
        self._cache_valid = False