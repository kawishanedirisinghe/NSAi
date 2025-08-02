
import os
import re
import glob
import asyncio
import subprocess
import tempfile
import json
import shutil
from pathlib import Path
from typing import Any, List, Optional, Dict
from app.tool import BaseTool
import logging

logger = logging.getLogger(__name__)

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
        result = f"📢 **Notification**: {text}"
        if attachments:
            result += f"\n\n📎 **Attachments**:\n"
            for attachment in attachments:
                result += f"- {attachment}\n"
        return result

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
        result = f"❓ **Question**: {text}"
        if attachments:
            result += f"\n\n📎 **Reference Materials**:\n"
            for attachment in attachments:
                result += f"- {attachment}\n"
        if suggest_user_takeover != "none":
            result += f"\n💡 **Suggestion**: Consider {suggest_user_takeover} takeover for this task."
        return result

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
        try:
            if not os.path.exists(file):
                return f"❌ Error: File '{file}' does not exist"
            
            if sudo:
                # Use sudo to read file
                cmd = ["sudo", "cat", file]
                if start_line is not None and end_line is not None:
                    cmd = ["sudo", "sed", "-n", f"{start_line + 1},{end_line}p", file]
                elif start_line is not None:
                    cmd = ["sudo", "sed", "-n", f"{start_line + 1},$p", file]
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if result.returncode != 0:
                    return f"❌ Error reading file with sudo: {result.stderr}"
                content = result.stdout
            else:
                # Read file normally
                with open(file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                if start_line is not None or end_line is not None:
                    start = start_line if start_line is not None else 0
                    end = end_line if end_line is not None else len(lines)
                    lines = lines[start:end]
                
                content = ''.join(lines)
            
            if not content.strip():
                return f"📄 File '{file}' is empty"
            
            return f"📄 **File Content** (`{file}`):\n```\n{content}\n```"
            
        except Exception as e:
            return f"❌ Error reading file '{file}': {str(e)}"

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
        try:
            # Prepare content
            final_content = content
            if leading_newline:
                final_content = "\n" + final_content
            if trailing_newline:
                final_content = final_content + "\n"
            
            if sudo:
                # Use sudo to write file
                mode = "a" if append else "w"
                temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False)
                temp_file.write(final_content)
                temp_file.close()
                
                cmd = ["sudo", "tee", "-a" if append else "", file]
                if not append:
                    cmd = ["sudo", "tee", file]
                
                with open(temp_file.name, 'r') as f:
                    result = subprocess.run(cmd, input=f.read(), capture_output=True, text=True, timeout=30)
                
                os.unlink(temp_file.name)
                
                if result.returncode != 0:
                    return f"❌ Error writing file with sudo: {result.stderr}"
            else:
                # Write file normally
                mode = "a" if append else "w"
                with open(file, mode, encoding='utf-8') as f:
                    f.write(final_content)
            
            action = "appended to" if append else "written to"
            return f"✅ Content {action} file: `{file}`"
            
        except Exception as e:
            return f"❌ Error writing to file '{file}': {str(e)}"

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
        try:
            if not os.path.exists(file):
                return f"❌ Error: File '{file}' does not exist"
            
            if sudo:
                # Use sed with sudo for replacement
                escaped_old = old_str.replace('/', '\\/')
                escaped_new = new_str.replace('/', '\\/')
                cmd = ["sudo", "sed", "-i", f"s/{escaped_old}/{escaped_new}/g", file]
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if result.returncode != 0:
                    return f"❌ Error replacing string with sudo: {result.stderr}"
            else:
                # Read file, replace content, write back
                with open(file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                if old_str not in content:
                    return f"⚠️ String '{old_str}' not found in file '{file}'"
                
                new_content = content.replace(old_str, new_str)
                
                with open(file, 'w', encoding='utf-8') as f:
                    f.write(new_content)
            
            return f"✅ Replaced '{old_str}' with '{new_str}' in file: `{file}`"
            
        except Exception as e:
            return f"❌ Error replacing string in file '{file}': {str(e)}"

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
        try:
            if not os.path.exists(file):
                return f"❌ Error: File '{file}' does not exist"
            
            if sudo:
                # Use grep with sudo
                cmd = ["sudo", "grep", "-E", regex, file]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                
                if result.returncode == 0:
                    matches = result.stdout.strip().split('\n')
                    return f"🔍 **Matches found in '{file}'**:\n```\n{result.stdout}\n```"
                elif result.returncode == 1:
                    return f"🔍 No matches found for regex '{regex}' in file '{file}'"
                else:
                    return f"❌ Error searching file with sudo: {result.stderr}"
            else:
                # Read file and search with regex
                with open(file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                pattern = re.compile(regex)
                matches = pattern.findall(content)
                
                if matches:
                    return f"🔍 **Matches found in '{file}'**:\n```\n{chr(10).join(matches)}\n```"
                else:
                    return f"🔍 No matches found for regex '{regex}' in file '{file}'"
            
        except Exception as e:
            return f"❌ Error searching file '{file}': {str(e)}"

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
        try:
            if not os.path.exists(path):
                return f"❌ Error: Directory '{path}' does not exist"
            
            if not os.path.isdir(path):
                return f"❌ Error: '{path}' is not a directory"
            
            # Use glob to find files
            search_pattern = os.path.join(path, glob)
            matching_files = glob.glob(search_pattern)
            
            if matching_files:
                file_list = []
                for file_path in matching_files:
                    if os.path.isfile(file_path):
                        size = os.path.getsize(file_path)
                        file_list.append(f"📄 {file_path} ({size} bytes)")
                    elif os.path.isdir(file_path):
                        file_list.append(f"📁 {file_path}/")
                
                return f"🔍 **Files found in '{path}' matching '{glob}'**:\n```\n{chr(10).join(file_list)}\n```"
            else:
                return f"🔍 No files found in '{path}' matching pattern '{glob}'"
            
        except Exception as e:
            return f"❌ Error searching directory '{path}': {str(e)}"

# Shell session management
shell_sessions: Dict[str, Dict] = {}

class PythonExec(BaseTool):
    name: str = "python_exec"
    description: str = "Execute Python commands and scripts. Use for running Python code, installing packages, or managing Python environments."
    parameters: dict = {
        "type": "object",
        "properties": {
            "id": {
                "type": "string",
                "description": "Unique identifier of the target Python session"
            },
            "exec_dir": {
                "type": "string",
                "description": "Working directory for command execution (must use absolute path)"
            },
            "command": {
                "type": "string",
                "description": "Python command or script to execute"
            },
            "use_venv": {
                "type": "boolean",
                "description": "Whether to use virtual environment if available"
            }
        },
        "required": ["id", "exec_dir", "command"]
    }

    async def execute(self, *, id: str, exec_dir: str, command: str, use_venv: bool = False, **kwargs: Any) -> str:
        try:
            # Initialize Python session if it doesn't exist
            if id not in shell_sessions:
                shell_sessions[id] = {
                    'process': None,
                    'output': [],
                    'working_dir': exec_dir,
                    'status': 'idle'
                }
            
            session = shell_sessions[id]
            
            # Change to specified directory
            if not os.path.exists(exec_dir):
                return f"❌ Error: Directory '{exec_dir}' does not exist"
            
            # Prepare Python command
            if command.startswith('py ') or command.startswith('python '):
                # Already a Python command
                py_command = command
            else:
                # Treat as Python code to execute
                py_command = f"python -c \"{command}\""
            
            # Check for virtual environment
            if use_venv:
                venv_path = os.path.join(exec_dir, 'venv', 'bin', 'python')
                if os.path.exists(venv_path):
                    py_command = py_command.replace('python', venv_path)
                else:
                    venv_path = os.path.join(exec_dir, 'venv', 'Scripts', 'python.exe')
                    if os.path.exists(venv_path):
                        py_command = py_command.replace('python', venv_path)
            
            # Execute Python command
            try:
                result = subprocess.run(
                    py_command,
                    shell=True,
                    cwd=exec_dir,
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                
                output = result.stdout
                error = result.stderr
                
                # Store output in session
                session['output'].append({
                    'command': command,
                    'stdout': output,
                    'stderr': error,
                    'returncode': result.returncode,
                    'timestamp': asyncio.get_event_loop().time()
                })
                
                # Keep only last 10 outputs
                if len(session['output']) > 10:
                    session['output'] = session['output'][-10:]
                
                result_text = f"🐍 **Python command executed in session '{id}'**:\n```python\n{command}\n```\n"
                
                if output:
                    result_text += f"📤 **Output**:\n```\n{output}\n```\n"
                
                if error:
                    result_text += f"⚠️ **Errors**:\n```\n{error}\n```\n"
                
                result_text += f"🔢 **Exit code**: {result.returncode}"
                
                return result_text
                
            except subprocess.TimeoutExpired:
                return f"⏰ Python command timed out after 60 seconds: `{command}`"
            except Exception as e:
                return f"❌ Error executing Python command: {str(e)}"
            
        except Exception as e:
            return f"❌ Error in Python session '{id}': {str(e)}"

class PythonSessionView(BaseTool):
    name: str = "python_session_view"
    description: str = "View the content of a specified Python session. Use for checking command execution results or monitoring output."
    parameters: dict = {
        "type": "object",
        "properties": {
            "id": {
                "type": "string",
                "description": "Unique identifier of the target Python session"
            }
        },
        "required": ["id"]
    }

    async def execute(self, *, id: str, **kwargs: Any) -> str:
        try:
            if id not in shell_sessions:
                return f"❌ Error: Python session '{id}' does not exist"
            
            session = shell_sessions[id]
            
            if not session['output']:
                return f"📋 Python session '{id}' has no command history"
            
            result = f"📋 **Python Session '{id}' History**:\n"
            result += f"📁 **Working Directory**: {session['working_dir']}\n\n"
            
            for i, output in enumerate(session['output'], 1):
                result += f"**Command {i}**:\n```python\n{output['command']}\n```\n"
                
                if output['stdout']:
                    result += f"**Output**:\n```\n{output['stdout']}\n```\n"
                
                if output['stderr']:
                    result += f"**Errors**:\n```\n{output['stderr']}\n```\n"
                
                result += f"**Exit Code**: {output['returncode']}\n"
                result += "─" * 50 + "\n\n"
            
            return result
            
        except Exception as e:
            return f"❌ Error viewing Python session '{id}': {str(e)}"

class PythonSessionWait(BaseTool):
    name: str = "python_session_wait"
    description: str = "Wait for the running process in a specified Python session to return. Use after running commands that require longer runtime."
    parameters: dict = {
        "type": "object",
        "properties": {
            "id": {
                "type": "string",
                "description": "Unique identifier of the target Python session"
            },
            "seconds": {
                "type": "integer",
                "description": "Wait duration in seconds"
            }
        },
        "required": ["id"]
    }

    async def execute(self, *, id: str, seconds: int = 0, **kwargs: Any) -> str:
        try:
            if id not in shell_sessions:
                return f"❌ Error: Python session '{id}' does not exist"
            
            session = shell_sessions[id]
            
            if seconds > 0:
                await asyncio.sleep(seconds)
                return f"⏰ Waited {seconds} seconds for Python session '{id}'"
            else:
                return f"ℹ️ Python session '{id}' is ready (no wait time specified)"
            
        except Exception as e:
            return f"❌ Error waiting for Python session '{id}': {str(e)}"

# Additional advanced tools
class FileCopy(BaseTool):
    name: str = "file_copy"
    description: str = "Copy files or directories from source to destination. Use for backing up files or creating duplicates."
    parameters: dict = {
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "description": "Source file or directory path"
            },
            "destination": {
                "type": "string",
                "description": "Destination path"
            },
            "recursive": {
                "type": "boolean",
                "description": "Whether to copy directories recursively"
            }
        },
        "required": ["source", "destination"]
    }

    async def execute(self, *, source: str, destination: str, recursive: bool = False, **kwargs: Any) -> str:
        try:
            if not os.path.exists(source):
                return f"❌ Error: Source '{source}' does not exist"
            
            if os.path.isdir(source) and recursive:
                shutil.copytree(source, destination, dirs_exist_ok=True)
            else:
                shutil.copy2(source, destination)
            
            return f"✅ Copied '{source}' to '{destination}'"
            
        except Exception as e:
            return f"❌ Error copying '{source}' to '{destination}': {str(e)}"

class FileDelete(BaseTool):
    name: str = "file_delete"
    description: str = "Delete files or directories. Use for cleaning up temporary files or removing unwanted content."
    parameters: dict = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to file or directory to delete"
            },
            "recursive": {
                "type": "boolean",
                "description": "Whether to delete directories recursively"
            }
        },
        "required": ["path"]
    }

    async def execute(self, *, path: str, recursive: bool = False, **kwargs: Any) -> str:
        try:
            if not os.path.exists(path):
                return f"❌ Error: Path '{path}' does not exist"
            
            if os.path.isdir(path) and recursive:
                shutil.rmtree(path)
            else:
                os.remove(path)
            
            return f"✅ Deleted '{path}'"
            
        except Exception as e:
            return f"❌ Error deleting '{path}': {str(e)}"

class DirectoryCreate(BaseTool):
    name: str = "directory_create"
    description: str = "Create directories. Use for organizing files or setting up project structure."
    parameters: dict = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Directory path to create"
            },
            "parents": {
                "type": "boolean",
                "description": "Whether to create parent directories if they don't exist"
            }
        },
        "required": ["path"]
    }

    async def execute(self, *, path: str, parents: bool = True, **kwargs: Any) -> str:
        try:
            os.makedirs(path, exist_ok=True)
            return f"✅ Created directory '{path}'"
            
        except Exception as e:
            return f"❌ Error creating directory '{path}': {str(e)}"

class ProcessList(BaseTool):
    name: str = "process_list"
    description: str = "List running processes. Use for monitoring system activity or finding specific processes."
    parameters: dict = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Optional pattern to filter processes"
            }
        },
        "required": []
    }

    async def execute(self, *, pattern: str = "", **kwargs: Any) -> str:
        try:
            cmd = ["ps", "aux"]
            if pattern:
                cmd.extend(["|", "grep", pattern])
            
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                return f"🖥️ **Running Processes**:\n```\n{result.stdout}\n```"
            else:
                return f"❌ Error listing processes: {result.stderr}"
            
        except Exception as e:
            return f"❌ Error listing processes: {str(e)}"

class SystemInfo(BaseTool):
    name: str = "system_info"
    description: str = "Get system information. Use for monitoring system resources or debugging."
    parameters: dict = {
        "type": "object",
        "properties": {},
        "required": []
    }

    async def execute(self, **kwargs: Any) -> str:
        try:
            info = {}
            
            # CPU info
            try:
                with open('/proc/cpuinfo', 'r') as f:
                    cpu_info = f.read()
                    info['cpu'] = cpu_info.split('\n')[0].split(':')[1].strip()
            except:
                info['cpu'] = "Unknown"
            
            # Memory info
            try:
                with open('/proc/meminfo', 'r') as f:
                    mem_info = f.read()
                    total_mem = int(mem_info.split('\n')[0].split()[1]) // 1024
                    info['memory'] = f"{total_mem} MB"
            except:
                info['memory'] = "Unknown"
            
            # Disk usage
            try:
                result = subprocess.run(['df', '-h', '/'], capture_output=True, text=True)
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')
                    if len(lines) > 1:
                        disk_info = lines[1].split()
                        info['disk'] = f"{disk_info[1]} total, {disk_info[2]} used, {disk_info[3]} available"
            except:
                info['disk'] = "Unknown"
            
            # OS info
            try:
                with open('/etc/os-release', 'r') as f:
                    os_info = f.read()
                    for line in os_info.split('\n'):
                        if line.startswith('PRETTY_NAME='):
                            info['os'] = line.split('=')[1].strip('"')
                            break
            except:
                info['os'] = "Unknown"
            
            result = "🖥️ **System Information**:\n"
            for key, value in info.items():
                result += f"**{key.title()}**: {value}\n"
            
            return result
            
        except Exception as e:
            return f"❌ Error getting system information: {str(e)}"

# Additional advanced tools
class PythonPackageManager(BaseTool):
    name: str = "python_package_manager"
    description: str = "Manage Python packages. Install, uninstall, or list packages in the current environment."
    parameters: dict = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["install", "uninstall", "list", "show", "search"],
                "description": "Action to perform"
            },
            "package": {
                "type": "string",
                "description": "Package name to install/uninstall/search"
            },
            "version": {
                "type": "string",
                "description": "Package version (optional)"
            }
        },
        "required": ["action"]
    }

    async def execute(self, *, action: str, package: str = "", version: str = "", **kwargs: Any) -> str:
        try:
            if action == "install" and package:
                cmd = f"pip install {package}"
                if version:
                    cmd += f"=={version}"
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
                return f"📦 **Package Installation**:\n```\n{result.stdout}\n{result.stderr}\n```"
            
            elif action == "uninstall" and package:
                cmd = f"pip uninstall {package} -y"
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
                return f"🗑️ **Package Uninstallation**:\n```\n{result.stdout}\n{result.stderr}\n```"
            
            elif action == "list":
                result = subprocess.run("pip list", shell=True, capture_output=True, text=True, timeout=30)
                return f"📋 **Installed Packages**:\n```\n{result.stdout}\n```"
            
            elif action == "show" and package:
                result = subprocess.run(f"pip show {package}", shell=True, capture_output=True, text=True, timeout=30)
                return f"ℹ️ **Package Info**:\n```\n{result.stdout}\n```"
            
            elif action == "search" and package:
                result = subprocess.run(f"pip search {package}", shell=True, capture_output=True, text=True, timeout=30)
                return f"🔍 **Package Search**:\n```\n{result.stdout}\n```"
            
            else:
                return "❌ Invalid action or missing package name"
                
        except Exception as e:
            return f"❌ Error in package management: {str(e)}"

class GitOperations(BaseTool):
    name: str = "git_operations"
    description: str = "Perform Git operations. Clone, pull, push, commit, and manage repositories."
    parameters: dict = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["clone", "pull", "push", "commit", "status", "log", "branch"],
                "description": "Git action to perform"
            },
            "repository": {
                "type": "string",
                "description": "Repository URL or path"
            },
            "message": {
                "type": "string",
                "description": "Commit message"
            },
            "branch": {
                "type": "string",
                "description": "Branch name"
            }
        },
        "required": ["action"]
    }

    async def execute(self, *, action: str, repository: str = "", message: str = "", branch: str = "", **kwargs: Any) -> str:
        try:
            if action == "clone" and repository:
                result = subprocess.run(f"git clone {repository}", shell=True, capture_output=True, text=True, timeout=300)
                return f"📥 **Git Clone**:\n```\n{result.stdout}\n{result.stderr}\n```"
            
            elif action == "pull":
                result = subprocess.run("git pull", shell=True, capture_output=True, text=True, timeout=60)
                return f"⬇️ **Git Pull**:\n```\n{result.stdout}\n{result.stderr}\n```"
            
            elif action == "push":
                result = subprocess.run("git push", shell=True, capture_output=True, text=True, timeout=60)
                return f"⬆️ **Git Push**:\n```\n{result.stdout}\n{result.stderr}\n```"
            
            elif action == "commit" and message:
                result = subprocess.run(f'git commit -m "{message}"', shell=True, capture_output=True, text=True, timeout=30)
                return f"💾 **Git Commit**:\n```\n{result.stdout}\n{result.stderr}\n```"
            
            elif action == "status":
                result = subprocess.run("git status", shell=True, capture_output=True, text=True, timeout=30)
                return f"📊 **Git Status**:\n```\n{result.stdout}\n```"
            
            elif action == "log":
                result = subprocess.run("git log --oneline -10", shell=True, capture_output=True, text=True, timeout=30)
                return f"📜 **Git Log**:\n```\n{result.stdout}\n```"
            
            elif action == "branch":
                result = subprocess.run("git branch -a", shell=True, capture_output=True, text=True, timeout=30)
                return f"🌿 **Git Branches**:\n```\n{result.stdout}\n```"
            
            else:
                return "❌ Invalid action or missing parameters"
                
        except Exception as e:
            return f"❌ Error in Git operations: {str(e)}"

class DatabaseOperations(BaseTool):
    name: str = "database_operations"
    description: str = "Perform database operations. Connect, query, and manage databases."
    parameters: dict = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["query", "execute", "backup", "restore"],
                "description": "Database action to perform"
            },
            "database": {
                "type": "string",
                "description": "Database name or connection string"
            },
            "query": {
                "type": "string",
                "description": "SQL query to execute"
            },
            "backup_path": {
                "type": "string",
                "description": "Backup file path"
            }
        },
        "required": ["action"]
    }

    async def execute(self, *, action: str, database: str = "", query: str = "", backup_path: str = "", **kwargs: Any) -> str:
        try:
            if action == "query" and database and query:
                # For SQLite
                if database.endswith('.db') or database.endswith('.sqlite'):
                    result = subprocess.run(f"sqlite3 {database} '{query}'", shell=True, capture_output=True, text=True, timeout=30)
                    return f"🗄️ **Database Query**:\n```\n{result.stdout}\n{result.stderr}\n```"
                else:
                    return "❌ Only SQLite databases are supported in this version"
            
            elif action == "backup" and database and backup_path:
                if database.endswith('.db') or database.endswith('.sqlite'):
                    result = subprocess.run(f"sqlite3 {database} '.backup {backup_path}'", shell=True, capture_output=True, text=True, timeout=60)
                    return f"💾 **Database Backup**:\n```\n{result.stdout}\n{result.stderr}\n```"
                else:
                    return "❌ Only SQLite databases are supported in this version"
            
            else:
                return "❌ Invalid action or missing parameters"
                
        except Exception as e:
            return f"❌ Error in database operations: {str(e)}"

class NetworkOperations(BaseTool):
    name: str = "network_operations"
    description: str = "Perform network operations. Ping, curl, wget, and network diagnostics."
    parameters: dict = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["ping", "curl", "wget", "nslookup", "traceroute"],
                "description": "Network action to perform"
            },
            "target": {
                "type": "string",
                "description": "Target URL or IP address"
            },
            "options": {
                "type": "string",
                "description": "Additional options"
            }
        },
        "required": ["action", "target"]
    }

    async def execute(self, *, action: str, target: str, options: str = "", **kwargs: Any) -> str:
        try:
            if action == "ping":
                cmd = f"ping -c 4 {target}"
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
                return f"🏓 **Ping Test**:\n```\n{result.stdout}\n{result.stderr}\n```"
            
            elif action == "curl":
                cmd = f"curl {options} {target}"
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
                return f"🌐 **Curl Request**:\n```\n{result.stdout}\n{result.stderr}\n```"
            
            elif action == "wget":
                cmd = f"wget {options} {target}"
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
                return f"⬇️ **Wget Download**:\n```\n{result.stdout}\n{result.stderr}\n```"
            
            elif action == "nslookup":
                cmd = f"nslookup {target}"
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
                return f"🔍 **DNS Lookup**:\n```\n{result.stdout}\n{result.stderr}\n```"
            
            elif action == "traceroute":
                cmd = f"traceroute {target}"
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
                return f"🛣️ **Traceroute**:\n```\n{result.stdout}\n{result.stderr}\n```"
            
            else:
                return "❌ Invalid network action"
                
        except Exception as e:
            return f"❌ Error in network operations: {str(e)}"

class SystemMonitoring(BaseTool):
    name: str = "system_monitoring"
    description: str = "Monitor system resources and performance. CPU, memory, disk, and network usage."
    parameters: dict = {
        "type": "object",
        "properties": {
            "metric": {
                "type": "string",
                "enum": ["cpu", "memory", "disk", "network", "processes", "all"],
                "description": "Metric to monitor"
            },
            "duration": {
                "type": "integer",
                "description": "Monitoring duration in seconds"
            }
        },
        "required": ["metric"]
    }

    async def execute(self, *, metric: str, duration: int = 5, **kwargs: Any) -> str:
        try:
            if metric == "cpu":
                result = subprocess.run("top -bn1 | grep 'Cpu(s)'", shell=True, capture_output=True, text=True, timeout=10)
                return f"🖥️ **CPU Usage**:\n```\n{result.stdout}\n```"
            
            elif metric == "memory":
                result = subprocess.run("free -h", shell=True, capture_output=True, text=True, timeout=10)
                return f"💾 **Memory Usage**:\n```\n{result.stdout}\n```"
            
            elif metric == "disk":
                result = subprocess.run("df -h", shell=True, capture_output=True, text=True, timeout=10)
                return f"💿 **Disk Usage**:\n```\n{result.stdout}\n```"
            
            elif metric == "network":
                result = subprocess.run("netstat -i", shell=True, capture_output=True, text=True, timeout=10)
                return f"🌐 **Network Interfaces**:\n```\n{result.stdout}\n```"
            
            elif metric == "processes":
                result = subprocess.run("ps aux --sort=-%cpu | head -10", shell=True, capture_output=True, text=True, timeout=10)
                return f"⚙️ **Top Processes**:\n```\n{result.stdout}\n```"
            
            elif metric == "all":
                result = subprocess.run("top -bn1", shell=True, capture_output=True, text=True, timeout=10)
                return f"📊 **System Overview**:\n```\n{result.stdout}\n```"
            
            else:
                return "❌ Invalid metric"
                
        except Exception as e:
            return f"❌ Error in system monitoring: {str(e)}"

class FileCompression(BaseTool):
    name: str = "file_compression"
    description: str = "Compress and decompress files. Support for zip, tar, gzip formats."
    parameters: dict = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["compress", "decompress"],
                "description": "Compression action"
            },
            "source": {
                "type": "string",
                "description": "Source file or directory"
            },
            "destination": {
                "type": "string",
                "description": "Destination file"
            },
            "format": {
                "type": "string",
                "enum": ["zip", "tar", "gzip"],
                "description": "Compression format"
            }
        },
        "required": ["action", "source"]
    }

    async def execute(self, *, action: str, source: str, destination: str = "", format: str = "zip", **kwargs: Any) -> str:
        try:
            if not destination:
                if action == "compress":
                    destination = f"{source}.{format}"
                else:
                    destination = source.rsplit('.', 1)[0]
            
            if action == "compress":
                if format == "zip":
                    cmd = f"zip -r {destination} {source}"
                elif format == "tar":
                    cmd = f"tar -czf {destination}.tar.gz {source}"
                elif format == "gzip":
                    cmd = f"gzip -c {source} > {destination}"
                
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
                return f"🗜️ **File Compression**:\n```\n{result.stdout}\n{result.stderr}\n```"
            
            elif action == "decompress":
                if format == "zip":
                    cmd = f"unzip {source} -d {destination}"
                elif format == "tar":
                    cmd = f"tar -xzf {source} -C {destination}"
                elif format == "gzip":
                    cmd = f"gunzip -c {source} > {destination}"
                
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
                return f"📦 **File Decompression**:\n```\n{result.stdout}\n{result.stderr}\n```"
            
            else:
                return "❌ Invalid action"
                
        except Exception as e:
            return f"❌ Error in file compression: {str(e)}"

class TextProcessing(BaseTool):
    name: str = "text_processing"
    description: str = "Process and analyze text files. Search, replace, sort, and filter text content."
    parameters: dict = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["search", "replace", "sort", "filter", "count", "stats"],
                "description": "Text processing action"
            },
            "file": {
                "type": "string",
                "description": "Input file path"
            },
            "pattern": {
                "type": "string",
                "description": "Search pattern or regex"
            },
            "replacement": {
                "type": "string",
                "description": "Replacement text"
            },
            "output": {
                "type": "string",
                "description": "Output file path"
            }
        },
        "required": ["action", "file"]
    }

    async def execute(self, *, action: str, file: str, pattern: str = "", replacement: str = "", output: str = "", **kwargs: Any) -> str:
        try:
            if not os.path.exists(file):
                return f"❌ File '{file}' does not exist"
            
            if action == "search" and pattern:
                cmd = f"grep -n '{pattern}' {file}"
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
                return f"🔍 **Text Search**:\n```\n{result.stdout}\n{result.stderr}\n```"
            
            elif action == "replace" and pattern and replacement:
                if not output:
                    output = f"{file}.new"
                cmd = f"sed 's/{pattern}/{replacement}/g' {file} > {output}"
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
                return f"🔄 **Text Replacement**:\n```\n{result.stdout}\n{result.stderr}\n```"
            
            elif action == "sort":
                if not output:
                    output = f"{file}.sorted"
                cmd = f"sort {file} > {output}"
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
                return f"📊 **Text Sorting**:\n```\n{result.stdout}\n{result.stderr}\n```"
            
            elif action == "filter" and pattern:
                if not output:
                    output = f"{file}.filtered"
                cmd = f"grep '{pattern}' {file} > {output}"
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
                return f"🔍 **Text Filtering**:\n```\n{result.stdout}\n{result.stderr}\n```"
            
            elif action == "count":
                cmd = f"wc -l {file}"
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
                return f"📊 **Line Count**:\n```\n{result.stdout}\n```"
            
            elif action == "stats":
                cmd = f"wc {file}"
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
                return f"📈 **File Statistics**:\n```\n{result.stdout}\n```"
            
            else:
                return "❌ Invalid action or missing parameters"
                
        except Exception as e:
            return f"❌ Error in text processing: {str(e)}"
