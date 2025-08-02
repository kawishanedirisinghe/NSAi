
from typing import Dict, List, Optional

from pydantic import Field, model_validator

from app.agent.browser import BrowserContextHelper
from app.agent.toolcall import ToolCallAgent
from app.config import config
from app.logger import logger
from app.prompt.manus import NEXT_STEP_PROMPT
from app.tool import Terminate, ToolCollection
from app.tool.ask_human import AskHuman
from app.tool.browser_use_tool import BrowserUseTool
from app.tool.mcp import MCPClients, MCPClientTool
from app.tool.python_execute import PythonExecute
from app.tool.str_replace_editor import StrReplaceEditor
from app.tool.manus_tools import (
    MessageNotifyUser,
    MessageAskUser,
    FileRead,
    FileWrite,
    FileStrReplace,
    FileFindInContent,
    FileFindByName,
    ShellExec,
    ShellView,
    ShellWait,
)

SYSTEM_PROMPT = """
You are Manus, an AI agent created by the Manus team.

<intro>
You excel at the following tasks:
1. Information gathering, fact-checking, and documentation
2. Data processing, analysis, and visualization
3. Writing multi-chapter articles and in-depth research reports
4. Creating websites, applications, and tools
5. Using programming to solve various problems beyond development
6. Various tasks that can be accomplished using computers and the internet
</intro>

<language_settings>
- Default working language: **English**
- Use the language specified by user in messages as the working language when explicitly provided
- All thinking and responses must be in the working language
- Natural language arguments in tool calls must be in the working language
- Avoid using pure lists and bullet points format in any language
</language_settings>

<system_capability>
- Communicate with users through message tools
- Access a Linux sandbox environment with internet connection
- Use shell, text editor, browser, and other software
- Write and run code in Python and various programming languages
- Independently install required software packages and dependencies via shell
- Deploy websites or applications and provide public access
- Suggest users to temporarily take control of the browser for sensitive operations when necessary
- Utilize various tools to complete user-assigned tasks step by step
</system_capability>

<event_stream>
You will be provided with a chronological event stream (may be truncated or partially omitted) containing the following types of events:
1. Message: Messages input by actual users
2. Action: Tool use (function calling) actions
3. Observation: Results generated from corresponding action execution
4. Plan: Task step planning and status updates provided by the Planner module
5. Knowledge: Task-related knowledge and best practices provided by the Knowledge module
6. Datasource: Data API documentation provided by the Datasource module
7. Other miscellaneous events generated during system operation
</event_stream>

<agent_loop>
You are operating in an agent loop, iteratively completing tasks through these steps:
1. Analyze Events: Understand user needs and current state through event stream, focusing on latest user messages and execution results
2. Select Tools: Choose next tool call based on current state, task planning, relevant knowledge and available data APIs
3. Wait for Execution: Selected tool action will be executed by sandbox environment with new observations added to event stream
4. Iterate: Choose only one tool call per iteration, patiently repeat above steps until task completion
5. Submit Results: Send results to user via message tools, providing deliverables and related files as message attachments
6. Enter Standby: Enter idle state when all tasks are completed or user explicitly requests to stop, and wait for new tasks
</agent_loop>

<planner_module>
- System is equipped with planner module for overall task planning
- Task planning will be provided as events in the event stream
- Task plans use numbered pseudocode to represent execution steps
- Each planning update includes the current step number, status, and reflection
- Pseudocode representing execution steps will update when overall task objective changes
- Must complete all planned steps and reach the final step number by completion
</planner_module>

<knowledge_module>
- System is equipped with knowledge and memory module for best practice references
- Task-relevant knowledge will be provided as events in the event stream
- Each knowledge item has its scope and should only be adopted when conditions are met
</knowledge_module>

<datasource_module>
- System is equipped with data API module for accessing authoritative datasources
- Available data APIs and their documentation will be provided as events in the event stream
- Only use data APIs already existing in the event stream; fabricating non-existent APIs is prohibited
- Prioritize using APIs for data retrieval; only use public internet when data APIs cannot meet requirements
- Data API usage costs are covered by the system, no login or authorization needed
- Data APIs must be called through Python code and cannot be used as tools
- Python libraries for data APIs are pre-installed in the environment, ready to use after import
- Save retrieved data to files instead of outputting intermediate results
</datasource_module>

<datasource_module_code_example>
weather.py:
\`\`\`python
import sys
sys.path.append('/opt/.manus/.sandbox-runtime')
from data_api import ApiClient
client = ApiClient()
# Use fully-qualified API names and parameters as specified in API documentation events.
# Always use complete query parameter format in query={...}, never omit parameter names.
weather = client.call_api('WeatherBank/get_weather', query={'location': 'Singapore'})
print(weather)
# --snip--
\`\`\`
</datasource_module_code_example>

<todo_rules>
- Create todo.md file as checklist based on task planning from the Planner module
- Task planning takes precedence over todo.md, while todo.md contains more details
- Update markers in todo.md via text replacement tool immediately after completing each item
- Rebuild todo.md when task planning changes significantly
- Must use todo.md to record and update progress for information gathering tasks
- When all planned steps are complete, verify todo.md completion and remove skipped items
</todo_rules>

<message_rules>
- Communicate with users via message tools instead of direct text responses
- Reply immediately to new user messages before other operations
- First reply must be brief, only confirming receipt without specific solutions
- Events from Planner, Knowledge, and Datasource modules are system-generated, no reply needed
- Notify users with brief explanation whenchanging methods or strategies
- Message tools are divided into notify (non-blocking, no reply needed from users) and ask (blocking, reply required)
- Actively use notify for progress updates, but reserve ask for only essential needs to minimize user disruption and avoid blocking progress
- Provide all relevant files as attachments, as users may not have direct access to local filesystem
- Must message users with results and deliverables before entering idle state upon task completion
</message_rules>

<file_rules>
- Use file tools for reading, writing, appending, and editing to avoid string escape issues in shell commands
- Actively save intermediate results and store different types of reference information in separate files
- When merging text files, must use append mode of file writing tool to concatenate content to target file
- Strictly follow requirements in <writing_rules>, and avoid using list formats in any files except todo.md
</file_rules>

<info_rules>
- Information priority: authoritative data from datasource API > web search > model's internal knowledge
- Prefer dedicated search tools over browser access to search engine result pages
- Snippets in search results are not valid sources; must access original pages via browser
- Access multiple URLs from search results for comprehensive information or cross-validation
- Conduct searches step by step: search multiple attributes of single entity separately, process multiple entities one by one
</info_rules>

<browser_rules>
- Must use browser tools to access and comprehend all URLs provided by users in messages
- Must use browser tools to access URLs from search tool results
- Actively explore valuable links for deeper information, either by clicking elements or accessing URLs directly
- Browser tools only return elements in visible viewport by default
- Visible elements are returned as \`index[:]<tag>text</tag>\`, where index is for interactive elements in subsequent browser actions
- Due to technical limitations, not all interactive elements may be identified; use coordinates to interact with unlisted elements
- Browser tools automatically attempt to extract page content, providing it in Markdown format if successful
- Extracted Markdown includes text beyond viewport but omits links and images; completeness not guaranteed
- If extracted Markdown is complete and sufficient for the task, no scrolling is needed; otherwise, must actively scroll to view the entire page
- Use message tools to suggest user to take over the browser for sensitive operations or actions with side effects when necessary
</browser_rules>

<shell_rules>
- Avoid commands requiring confirmation; actively use -y or -f flags for automatic confirmation
- Avoid commands with excessive output; save to files when necessary
- Chain multiple commands with && operator to minimize interruptions
- Use pipe operator to pass command outputs, simplifying operations
- Use non-interactive \`bc\` for simple calculations, Python for complex ones
</shell_rules>
"""



class Manus(ToolCallAgent):

    name: str = "Manus"
    description: str = "A versatile agent that can solve various tasks using multiple tools including MCP-based tools"

    system_prompt: str = SYSTEM_PROMPT

    next_step_prompt: str = NEXT_STEP_PROMPT

    max_observe: int = 10000
    max_steps: int = 500

    # MCP clients for remote tool access
    mcp_clients: MCPClients = Field(default_factory=MCPClients)

    # Add general-purpose tools to the tool collection
    available_tools: ToolCollection = Field(
        default_factory=lambda: ToolCollection(
            PythonExecute(),
            BrowserUseTool(),
            StrReplaceEditor(),
            AskHuman(),
            Terminate(),
            MessageNotifyUser(),
            MessageAskUser(),
            FileRead(),
            FileWrite(),
            FileStrReplace(),
            FileFindInContent(),
            FileFindByName(),
            ShellExec(),
            ShellView(),
            ShellWait(),
        )
    )

    special_tool_names: list[str] = Field(default_factory=lambda: [Terminate().name])
    browser_context_helper: Optional[BrowserContextHelper] = None

    # Track connected MCP servers
    connected_servers: Dict[str, str] = Field(
        default_factory=dict
    )  # server_id -> url/command
    _initialized: bool = False

    # Advanced API key management
    api_key_manager: Optional[object] = Field(default=None, exclude=True)
    current_key_config: Optional[Dict] = Field(default=None, exclude=True)
    retry_count: int = Field(default=0, exclude=True)

    # Stop signal tracking
    task_id: Optional[str] = Field(default=None, exclude=True)
    running_tasks: Optional[Dict] = Field(default=None, exclude=True)

    @model_validator(mode="after")
    def initialize_helper(self) -> "Manus":
        """Initialize basic components synchronously."""
        self.browser_context_helper = BrowserContextHelper(self)
        return self

    @classmethod
    async def create(cls, api_key_manager=None, task_id=None, running_tasks=None, **kwargs) -> "Manus":
        """Factory method to create and properly initialize a Manus instance."""
        # Use the advanced API key manager if provided
        if api_key_manager:
            # Get an available API key from the manager
            result = api_key_manager.get_available_api_key(use_random=True)
            if result:
                api_key, key_config = result
                kwargs['api_key'] = api_key
                kwargs['api_key_manager'] = api_key_manager
                kwargs['current_key_config'] = key_config

        # Add task tracking for stop functionality
        kwargs['task_id'] = task_id
        kwargs['running_tasks'] = running_tasks

        instance = cls(**kwargs)
        await instance.initialize_mcp_servers()
        instance._initialized = True
        return instance

    async def initialize_mcp_servers(self) -> None:
        """Initialize connections to configured MCP servers."""
        for server_id, server_config in config.mcp_config.servers.items():
            try:
                if server_config.type == "sse":
                    if server_config.url:
                        await self.connect_mcp_server(server_config.url, server_id)
                        logger.info(
                            f"Connected to MCP server {server_id} at {server_config.url}"
                        )
                elif server_config.type == "stdio":
                    if server_config.command:
                        await self.connect_mcp_server(
                            server_config.command,
                            server_id,
                            use_stdio=True,
                            stdio_args=server_config.args,
                        )
                        logger.info(
                            f"Connected to MCP server {server_id} using command {server_config.command}"
                        )
            except Exception as e:
                logger.error(f"Failed to connect to MCP server {server_id}: {e}")

    async def connect_mcp_server(
        self,
        server_url: str,
        server_id: str = "",
        use_stdio: bool = False,
        stdio_args: List[str] = None,
    ) -> None:
        """Connect to an MCP server and add its tools."""
        if use_stdio:
            await self.mcp_clients.connect_stdio(
                server_url, stdio_args or [], server_id
            )
            self.connected_servers[server_id or server_url] = server_url
        else:
            await self.mcp_clients.connect_sse(server_url, server_id)
            self.connected_servers[server_id or server_url] = server_url

        # Update available tools with only the new tools from this server
        new_tools = [
            tool for tool in self.mcp_clients.tools if tool.server_id == server_id
        ]
        self.available_tools.add_tools(*new_tools)

    async def disconnect_mcp_server(self, server_id: str = "") -> None:
        """Disconnect from an MCP server and remove its tools."""
        await self.mcp_clients.disconnect(server_id)
        if server_id:
            self.connected_servers.pop(server_id, None)
        else:
            self.connected_servers.clear()

        # Rebuild available tools without the disconnected server's tools
        base_tools = [
            tool
            for tool in self.available_tools.tools
            if not isinstance(tool, MCPClientTool)
        ]
        self.available_tools = ToolCollection(*base_tools)
        self.available_tools.add_tools(*self.mcp_clients.tools)

    async def cleanup(self):
        """Clean up Manus agent resources."""
        if self.browser_context_helper:
            await self.browser_context_helper.cleanup_browser()
        # Disconnect from all MCP servers only if we were initialized
        if self._initialized:
            await self.disconnect_mcp_server()
            self._initialized = False

    async def think(self) -> bool:
        """Process current state and decide next actions with advanced API key rotation."""
        if not self._initialized:
            await self.initialize_mcp_servers()
            self._initialized = True

        original_prompt = self.next_step_prompt
        recent_messages = self.memory.messages[-3:] if self.memory.messages else []
        browser_in_use = any(
            tc.function.name == BrowserUseTool().name
            for msg in recent_messages
            if msg.tool_calls
            for tc in msg.tool_calls
        )

        if browser_in_use:
            self.next_step_prompt = (
                await self.browser_context_helper.format_next_step_prompt()
            )

        # Enhanced error handling with API key rotation
        max_retries = 3 if self.api_key_manager else 1

        for attempt in range(max_retries):
            try:
                # Record successful request if using API key manager
                if self.api_key_manager and self.current_key_config:
                    current_api_key = self.current_key_config['api_key']

                result = await super().think()

                # Record successful request
                if self.api_key_manager and self.current_key_config:
                    self.api_key_manager.record_successful_request(current_api_key)
                    logger.info(f"Successful request with key: {self.current_key_config['name']}")

                # Restore original prompt and return result
                self.next_step_prompt = original_prompt
                return result

            except Exception as e:
                error_str = str(e).lower()

                # Handle API key rotation if manager is available
                if self.api_key_manager and self.current_key_config:
                    current_api_key = self.current_key_config['api_key']
                    key_name = self.current_key_config['name']

                    # Categorize the error and handle accordingly
                    if any(keyword in error_str for keyword in ["rate limit", "quota", "too many requests", "resource_exhausted"]):
                        logger.warning(f"Rate limit error with key {key_name}: {e}")
                        self.api_key_manager.record_rate_limit_error(current_api_key, key_name)
                    elif any(keyword in error_str for keyword in ["authentication", "invalid api key", "unauthorized"]):
                        logger.error(f"Authentication error with key {key_name}: {e}")
                        self.api_key_manager.record_failure(current_api_key, key_name, "auth_error")
                    elif any(keyword in error_str for keyword in ["timeout", "connection"]):
                        logger.warning(f"Connection error with key {key_name}: {e}")
                        self.api_key_manager.record_failure(current_api_key, key_name, "connection_error")
                    else:
                        logger.error(f"Unexpected error with key {key_name}: {e}")
                        self.api_key_manager.record_failure(current_api_key, key_name, "unknown_error")

                    # Try to get a different API key for retry
                    if attempt < max_retries - 1:
                        logger.info(f"Attempting to rotate API key (attempt {attempt + 1}/{max_retries})")

                        # Get next available API key
                        result = self.api_key_manager.get_available_api_key(use_random=True)
                        if result:
                            new_api_key, new_key_config = result
                            if new_api_key != current_api_key:  # Only rotate if different key
                                logger.info(f"Rotating to API key: {new_key_config['name']}")

                                # Update the LLM client with new API key
                                if hasattr(self.llm, 'client') and hasattr(self.llm.client, 'api_key'):
                                    self.llm.client.api_key = new_api_key
                                elif hasattr(self.llm, 'api_key'):
                                    self.llm.api_key = new_api_key

                                # Update current key config
                                self.current_key_config = new_key_config

                                # Add small delay before retry
                                import asyncio
                                await asyncio.sleep(1)
                                continue

                        logger.warning("No alternative API key available for rotation")

                # If this is the last attempt or no API key manager, raise the error
                if attempt == max_retries - 1:
                    # Log rotation stats if available
                    if self.api_key_manager:
                        rotation_stats = self.api_key_manager.get_keys_status()
                        logger.info(f"Final API Key Status: {len([k for k in rotation_stats if k['available']])} available keys")

                    # Restore original prompt before raising
                    self.next_step_prompt = original_prompt
                    raise e

        # This should not be reached, but restore prompt just in case
        self.next_step_prompt = original_prompt
        return False
