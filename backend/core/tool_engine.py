import json
from typing import Any, Dict, List, Tuple
from settings import OPENAPI_PATH

class ToolRegistry:
    """
    - Load OpenAPI schema
    - Build tools[] for OpenAI
    - Provide lookup: operationId -> {server_url, path, method}
    """

    def __init__(self, openapi_path: str = str(OPENAPI_PATH)):
        self.openapi_path = openapi_path
        self.schema: Dict[str, Any] = {}
        self.server_url: str = ""
        self.operations: Dict[str, Dict[str, Any]] = {}
        self.tools: List[Dict[str, Any]] = []

    def load(self):
        with open(self.openapi_path, "r", encoding="utf-8") as f:
            self.schema = json.load(f)

        servers = self.schema.get("servers") or []
        if not servers or not servers[0].get("url"):
            raise ValueError("OpenAPI schema missing servers[0].url")
        self.server_url = servers[0]["url"].rstrip("/")

        self.operations = self._parse_operations()
        self.tools = self._build_tools()
        self._register_custom_tools()

    def _register_custom_tools(self):
        self.operations["getChanSong"] = {
            "path": "",
            "method": "CUSTOM",
            "summary": "Lay lich su cac phien chuan bi tao day va xac nhan tao day.",
            "parameters": [],
        }
        self.tools.append({
            "type": "function",
            "function": {
                "name": "getChanSong",
                "description": (
                    "Lay toan bo lich su cac phien chuan bi tao day va xac nhan tao day. "
                    "Account duoc backend tu cau hinh, khong truyen tham so."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        })

    def _parse_operations(self) -> Dict[str, Dict[str, Any]]:
        ops: Dict[str, Dict[str, Any]] = {}
        paths = self.schema.get("paths", {})

        for path, methods in paths.items():
            for method, detail in (methods or {}).items():
                if not isinstance(detail, dict):
                    continue
                op_id = detail.get("operationId")
                if not op_id:
                    continue

                ops[op_id] = {
                    "path": path,
                    "method": method.upper(),
                    "summary": detail.get("summary", "") or detail.get("description", "") or op_id,
                    "parameters": detail.get("parameters", []) or [],
                }
        return ops

    def _param_schema_to_jsonschema(self, p: Dict[str, Any]) -> Tuple[str, Dict[str, Any], bool]:
        """
        OpenAPI parameter -> JSON schema property
        returns: (name, jsonschema, required)
        """
        name = p.get("name", "")
        required = bool(p.get("required", False))
        schema = p.get("schema", {}) or {}

        # Pass through useful schema fields if present
        prop: Dict[str, Any] = {}
        if "type" in schema:
            prop["type"] = schema["type"]
        else:
            prop["type"] = "string"

        for k in ["enum", "pattern", "format", "minimum", "maximum", "default", "description"]:
            if k in schema:
                prop[k] = schema[k]

        # If OpenAPI parameter has description, keep it
        if "description" in p and "description" not in prop:
            prop["description"] = p["description"]

        return name, prop, required

    def _build_tools(self) -> List[Dict[str, Any]]:
        tools: List[Dict[str, Any]] = []

        for op_id, meta in self.operations.items():
            properties: Dict[str, Any] = {}
            required_list: List[str] = []

            for p in meta.get("parameters", []):
                if not isinstance(p, dict):
                    continue
                pname, pschema, preq = self._param_schema_to_jsonschema(p)
                if not pname:
                    continue
                properties[pname] = pschema
                if preq:
                    required_list.append(pname)

            tool = {
                "type": "function",
                "function": {
                    "name": op_id,
                    "description": meta.get("summary", op_id),
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required_list,
                        "additionalProperties": False,
                    },
                },
            }
            tools.append(tool)

        return tools
