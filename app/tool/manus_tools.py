
from app.tool import BaseTool
from typing import Any, List, Optional

class MessageNotifyUser(BaseTool):
    name: str = "message_notify_user"
    description: str = "Send a message to user without requiring a response. Use for acknowledging receipt of messages, providing progress updates, reporting task completion, or explaining changes in approach."
    parameters: dict = {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Message text to display to user"
            },
            "attachments": {
                "anyOf": [
                    {"type": "string"},
                    {"items": {"type": "string"}, "type": "array"}
                ],
                "description": "(Optional) List of attachments to show to user, can be file paths or URLs"
            }
        },
        "required": ["text"]
    }

    async def execute(self, *, text: str, attachments: Optional[List[str]] = None, **kwargs: Any) -> str:
        # This is a placeholder implementation.
        # In a real scenario, this would send a notification to the user.
        return f"Notification sent to user: {text}"

class MessageAskUser(BaseTool):
    name: str = "message_ask_user"
    description: str = "Ask user a question and wait for response. Use for requesting clarification, asking for confirmation, or gathering additional information."
    parameters: dict = {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Question text to present to user"
            },
            "attachments": {
                "anyOf": [
                    {"type": "string"},
                    {"items": {"type": "string"}, "type": "array"}
                ],
                "description": "(Optional) List of question-related files or reference materials"
            },
            "suggest_user_takeover": {
                "type": "string",
                "enum": ["none", "browser"],
                "description": "(Optional) Suggested operation for user takeover"
            }
        },
        "required": ["text"]
    }

    async def execute(self, *, text: str, attachments: Optional[List[str]] = None, suggest_user_takeover: str = "none", **kwargs: Any) -> str:
        # This is a placeholder implementation.
        # In a real scenario, this would present a question to the user and wait for a response.
        return f"Question asked to user: {text}"


class FileRead(BaseTool):
    name: str = "file_read"
    description: str = "Read file content. Use for checking file contents, analyzing logs, or reading configuration files."
    parameters: dict = {
        "type": "object",
        "properties": {
            "file": {
                "type": "string",
                "description": "Absolute path of the file to read"
            },
            "start_line": {
                "type": "integer",
                "description": "(Optional) Starting line to read from, 0-based"
            },
            "end_line": {
                "type": "integer",
                "description": "(Optional) Ending line number (exclusive)"
            },
            "sudo": {
                "type": "boolean",
                "description": "(Optional) Whether to use sudo privileges"
            }
        },
        "required": ["file"]
    }

    async def execute(self, *, file: str, start_line: Optional[int] = None, end_line: Optional[int] = None, sudo: bool = False, **kwargs: Any) -> str:
        # This is a placeholder implementation.
        return f"Reading file: {file}"

class FileWrite(BaseTool):
    name: str = "file_write"
    description: str = "Overwrite or append content to a file. Use for creating new files, appending content, or modifying existing files."
    parameters: dict = {
        "type": "object",
        "properties": {
            "file": {
                "type": "string",
                "description": "Absolute path of the file to write to"
            },
            "content": {
                "type": "string",
                "description": "Text content to write"
            },
            "append": {
                "type": "boolean",
                "description": "(Optional) Whether to use append mode"
            },
            "leading_newline": {
                "type": "boolean",
                "description": "(Optional) Whether to add a leading newline"
            },
            "trailing_newline": {
                "type": "boolean",
                "description": "(Optional) Whether to add a trailing newline"
            },
            "sudo": {
                "type": "boolean",
                "description": "(Optional) Whether to use sudo privileges"
            }
        },
        "required": ["file", "content"]
    }

    async def execute(self, *, file: str, content: str, append: bool = False, leading_newline: bool = False, trailing_newline: bool = False, sudo: bool = False, **kwargs: Any) -> str:
        # This is a placeholder implementation.
        return f"Writing to file: {file}"

class FileStrReplace(BaseTool):
    name: str = "file_str_replace"
    description: str = "Replace specified string in a file. Use for updating specific content in files or fixing errors in code."
    parameters: dict = {
        "type": "object",
        "properties": {
            "file": {
                "type": "string",
                "description": "Absolute path of the file to perform replacement on"
            },
            "old_str": {
                "type": "string",
                "description": "Original string to be replaced"
            },
            "new_str": {
                "type": "string",
                "description": "New string to replace with"
            },
            "sudo": {
                "type": "boolean",
                "description": "(Optional) Whether to use sudo privileges"
            }
        },
        "required": ["file", "old_str", "new_str"]
    }

    async def execute(self, *, file: str, old_str: str, new_str: str, sudo: bool = False, **kwargs: Any) -> str:
        # This is a placeholder implementation.
        return f"Replacing string in file: {file}"

class FileFindInContent(BaseTool):
    name: str = "file_find_in_content"
    description: str = "Search for matching text within file content. Use for finding specific content or patterns in files."
    parameters: dict = {
        "type": "object",
        "properties": {
            "file": {
                "type": "string",
                "description": "Absolute path of the file to search within"
            },
            "regex": {
                "type": "string",
                "description": "Regular expression pattern to match"
            },
            "sudo": {
                "type": "boolean",
                "description": "(Optional) Whether to use sudo privileges"
            }
        },
        "required": ["file", "regex"]
    }

    async def execute(self, *, file: str, regex: str, sudo: bool = False, **kwargs: Any) -> str:
        # This is a placeholder implementation.
        return f"Finding content in file: {file}"

class FileFindByName(BaseTool):
    name: str = "file_find_by_name"
    description: str = "Find files by name pattern in specified directory. Use for locating files with specific naming patterns."
    parameters: dict = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute path of directory to search"
            },
            "glob": {
                "type": "string",
                "description": "Filename pattern using glob syntax wildcards"
            }
        },
        "required": ["path", "glob"]
    }

    async def execute(self, *, path: str, glob: str, **kwargs: Any) -> str:
        # This is a placeholder implementation.
        return f"Finding files in path: {path}"


class ShellExec(BaseTool):
    name: str = "shell_exec"
    description: str = "Execute commands in a specified shell session. Use for running code, installing packages, or managing files."
    parameters: dict = {
        "type": "object",
        "properties": {
            "id": {
                "type": "string",
                "description": "Unique identifier of the target shell session"
            },
            "exec_dir": {
                "type": "string",
                "description": "Working directory for command execution (must use absolute path)"
            },
            "command": {
                "type": "string",
                "description": "Shell command to execute"
            }
        },
        "required": ["id", "exec_dir", "command"]
    }

    async def execute(self, *, id: str, exec_dir: str, command: str, **kwargs: Any) -> str:
        # This is a placeholder implementation.
        return f"Executing command in shell {id}: {command}"

class ShellView(BaseTool):
    name: str = "shell_view"
    description: str = "View the content of a specified shell session. Use for checking command execution results or monitoring output."
    parameters: dict = {
        "type": "object",
        "properties": {
            "id": {
                "type": "string",
                "description": "Unique identifier of the target shell session"
            }
        },
        "required": ["id"]
    }

    async def execute(self, *, id: str, **kwargs: Any) -> str:
        # This is a placeholder implementation.
        return f"Viewing shell session: {id}"

class ShellWait(BaseTool):
    name: str = "shell_wait"
    description: str = "Wait for the running process in a specified shell session to return. Use after running commands that require longer runtime."
    parameters: dict = {
        "type": "object",
        "properties": {
            "id": {
                "type": "string",
                "description": "Unique identifier of the target shell session"
            },
            "seconds": {
                "type": "integer",
                "description": "Wait duration in seconds"
            }
        },
        "required": ["id"]
    }

    async def execute(self, *, id: str, seconds: int = 0, **kwargs: Any) -> str:
        # This is a placeholder implementation.
        return f"Waiting for shell session: {id}"
