import os
import sys
import subprocess
import tempfile
import signal
import threading
import time
import json
import logging
import resource
import ctypes
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
import docker
import psutil
import uuid
from datetime import datetime
import traceback

logger = logging.getLogger(__name__)

class SecurityViolation(Exception):
    """Exception raised when security restrictions are violated"""
    pass

class ResourceLimitExceeded(Exception):
    """Exception raised when resource limits are exceeded"""
    pass

class SandboxConfig:
    """Configuration for sandbox environment"""
    def __init__(self):
        # Resource limits
        self.max_cpu_time = 30  # seconds
        self.max_memory = 512 * 1024 * 1024  # 512MB
        self.max_disk_usage = 100 * 1024 * 1024  # 100MB
        self.max_processes = 10
        self.max_file_size = 10 * 1024 * 1024  # 10MB
        
        # Security restrictions
        self.allowed_modules = {
            'builtins', 'os', 'sys', 'math', 'random', 'datetime', 
            'json', 're', 'collections', 'itertools', 'functools',
            'pathlib', 'tempfile', 'shutil', 'glob', 'fnmatch',
            'urllib.parse', 'base64', 'hashlib', 'hmac', 'zlib',
            'gzip', 'bz2', 'lzma', 'pickle', 'copy', 'pprint',
            'typing', 'dataclasses', 'enum', 'abc', 'contextlib'
        }
        
        self.blocked_modules = {
            'subprocess', 'multiprocessing', 'threading', 'asyncio',
            'socket', 'ssl', 'http', 'urllib', 'requests', 'ftplib',
            'smtplib', 'poplib', 'imaplib', 'telnetlib', 'xmlrpc',
            'sqlite3', 'pickle', 'marshal', 'ctypes', 'mmap',
            'signal', 'pwd', 'grp', 'crypt', 'termios', 'tty',
            'pty', 'fcntl', 'select', 'epoll', 'kqueue', 'pipes',
            'fifo', 'shm', 'semaphore', 'msg', 'ipc', 'sysv_ipc'
        }
        
        self.allowed_functions = {
            'print', 'len', 'range', 'enumerate', 'zip', 'map', 'filter',
            'sorted', 'reversed', 'sum', 'min', 'max', 'abs', 'round',
            'pow', 'divmod', 'bin', 'oct', 'hex', 'chr', 'ord',
            'str', 'int', 'float', 'bool', 'list', 'tuple', 'dict',
            'set', 'frozenset', 'bytes', 'bytearray', 'memoryview',
            'open', 'input', 'eval', 'exec', 'compile', 'dir', 'vars',
            'getattr', 'setattr', 'hasattr', 'delattr', 'isinstance',
            'issubclass', 'super', 'property', 'staticmethod', 'classmethod'
        }
        
        self.blocked_functions = {
            'eval', 'exec', 'compile', '__import__', 'globals', 'locals',
            'vars', 'dir', 'getattr', 'setattr', 'hasattr', 'delattr'
        }
        
        # File system restrictions
        self.allowed_paths = {
            '/tmp', '/var/tmp', tempfile.gettempdir()
        }
        
        self.blocked_paths = {
            '/etc', '/var', '/usr', '/bin', '/sbin', '/lib', '/lib64',
            '/home', '/root', '/proc', '/sys', '/dev', '/boot'
        }

class SandboxMonitor:
    """Monitor for tracking resource usage and security violations"""
    def __init__(self, config: SandboxConfig):
        self.config = config
        self.start_time = None
        self.end_time = None
        self.cpu_usage = 0
        self.memory_usage = 0
        self.disk_usage = 0
        self.process_count = 0
        self.violations = []
        self.is_monitoring = False
        self.monitor_thread = None
        
    def start_monitoring(self, process_id: int):
        """Start monitoring a process"""
        self.start_time = time.time()
        self.is_monitoring = True
        self.monitor_thread = threading.Thread(
            target=self._monitor_process,
            args=(process_id,),
            daemon=True
        )
        self.monitor_thread.start()
        
    def stop_monitoring(self):
        """Stop monitoring"""
        self.is_monitoring = False
        self.end_time = time.time()
        if self.monitor_thread:
            self.monitor_thread.join(timeout=1)
            
    def _monitor_process(self, process_id: int):
        """Monitor process resource usage"""
        try:
            process = psutil.Process(process_id)
            
            while self.is_monitoring:
                try:
                    # Check CPU time
                    cpu_times = process.cpu_times()
                    cpu_time = cpu_times.user + cpu_times.system
                    
                    if cpu_time > self.config.max_cpu_time:
                        self.violations.append({
                            'type': 'cpu_limit_exceeded',
                            'value': cpu_time,
                            'limit': self.config.max_cpu_time,
                            'timestamp': time.time()
                        })
                        self.is_monitoring = False
                        break
                    
                    # Check memory usage
                    memory_info = process.memory_info()
                    if memory_info.rss > self.config.max_memory:
                        self.violations.append({
                            'type': 'memory_limit_exceeded',
                            'value': memory_info.rss,
                            'limit': self.config.max_memory,
                            'timestamp': time.time()
                        })
                        self.is_monitoring = False
                        break
                    
                    # Check process count
                    children = process.children(recursive=True)
                    if len(children) > self.config.max_processes:
                        self.violations.append({
                            'type': 'process_limit_exceeded',
                            'value': len(children),
                            'limit': self.config.max_processes,
                            'timestamp': time.time()
                        })
                        self.is_monitoring = False
                        break
                    
                    # Update metrics
                    self.cpu_usage = cpu_time
                    self.memory_usage = memory_info.rss
                    self.process_count = len(children)
                    
                    time.sleep(0.1)  # Check every 100ms
                    
                except psutil.NoSuchProcess:
                    break
                except Exception as e:
                    logger.error(f"Error monitoring process: {e}")
                    break
                    
        except Exception as e:
            logger.error(f"Error in monitor thread: {e}")
            
    def get_report(self) -> Dict:
        """Get monitoring report"""
        duration = (self.end_time or time.time()) - (self.start_time or 0)
        
        return {
            'duration': duration,
            'cpu_usage': self.cpu_usage,
            'memory_usage': self.memory_usage,
            'disk_usage': self.disk_usage,
            'process_count': self.process_count,
            'violations': self.violations,
            'has_violations': len(self.violations) > 0
        }

class CodeValidator:
    """Validate code for security and compliance"""
    def __init__(self, config: SandboxConfig):
        self.config = config
        
    def validate_code(self, code: str) -> Tuple[bool, List[str]]:
        """Validate code and return (is_valid, issues)"""
        issues = []
        
        # Check for blocked imports
        import_issues = self._check_imports(code)
        issues.extend(import_issues)
        
        # Check for blocked functions
        function_issues = self._check_functions(code)
        issues.extend(function_issues)
        
        # Check for dangerous patterns
        pattern_issues = self._check_patterns(code)
        issues.extend(pattern_issues)
        
        # Check for file system access
        filesystem_issues = self._check_filesystem_access(code)
        issues.extend(filesystem_issues)
        
        return len(issues) == 0, issues
    
    def _check_imports(self, code: str) -> List[str]:
        """Check for blocked imports"""
        issues = []
        lines = code.split('\n')
        
        for i, line in enumerate(lines, 1):
            line = line.strip()
            
            # Check import statements
            if line.startswith('import ') or line.startswith('from '):
                for blocked_module in self.config.blocked_modules:
                    if blocked_module in line:
                        issues.append(f"Line {i}: Blocked module '{blocked_module}' imported")
                        
        return issues
    
    def _check_functions(self, code: str) -> List[str]:
        """Check for blocked function calls"""
        issues = []
        lines = code.split('\n')
        
        for i, line in enumerate(lines, 1):
            line = line.strip()
            
            for blocked_func in self.config.blocked_functions:
                if f"{blocked_func}(" in line:
                    issues.append(f"Line {i}: Blocked function '{blocked_func}' called")
                    
        return issues
    
    def _check_patterns(self, code: str) -> List[str]:
        """Check for dangerous code patterns"""
        issues = []
        
        # Check for exec/eval usage
        if 'exec(' in code or 'eval(' in code:
            issues.append("Dangerous pattern: exec/eval usage detected")
            
        # Check for file system traversal
        if '../' in code or '..\\' in code:
            issues.append("Dangerous pattern: Directory traversal detected")
            
        # Check for shell command execution
        if 'os.system(' in code or 'subprocess.call(' in code:
            issues.append("Dangerous pattern: Shell command execution detected")
            
        return issues
    
    def _check_filesystem_access(self, code: str) -> List[str]:
        """Check for restricted file system access"""
        issues = []
        
        for blocked_path in self.config.blocked_paths:
            if blocked_path in code:
                issues.append(f"Restricted path access: {blocked_path}")
                
        return issues

class AdvancedSandbox:
    """Advanced sandbox environment for safe code execution"""
    def __init__(self, config: Optional[SandboxConfig] = None):
        self.config = config or SandboxConfig()
        self.validator = CodeValidator(self.config)
        self.monitor = SandboxMonitor(self.config)
        self.execution_history = []
        
    def execute_python(self, code: str, timeout: int = 30) -> Dict:
        """Execute Python code in sandbox"""
        execution_id = str(uuid.uuid4())
        start_time = time.time()
        
        try:
            # Validate code
            is_valid, issues = self.validator.validate_code(code)
            if not is_valid:
                return {
                    'success': False,
                    'error': 'Code validation failed',
                    'issues': issues,
                    'execution_id': execution_id,
                    'duration': time.time() - start_time
                }
            
            # Create temporary directory
            with tempfile.TemporaryDirectory() as temp_dir:
                # Write code to file
                code_file = Path(temp_dir) / "code.py"
                with open(code_file, 'w') as f:
                    f.write(code)
                
                # Set resource limits
                resource.setrlimit(resource.RLIMIT_CPU, (self.config.max_cpu_time, self.config.max_cpu_time))
                resource.setrlimit(resource.RLIMIT_AS, (self.config.max_memory, self.config.max_memory))
                resource.setrlimit(resource.RLIMIT_NOFILE, (100, 100))
                
                # Execute code
                result = self._execute_with_monitoring(code_file, timeout)
                
                # Record execution
                execution_record = {
                    'id': execution_id,
                    'code': code,
                    'result': result,
                    'timestamp': datetime.now().isoformat(),
                    'duration': time.time() - start_time
                }
                self.execution_history.append(execution_record)
                
                return result
                
        except Exception as e:
            error_result = {
                'success': False,
                'error': str(e),
                'traceback': traceback.format_exc(),
                'execution_id': execution_id,
                'duration': time.time() - start_time
            }
            
            # Record failed execution
            execution_record = {
                'id': execution_id,
                'code': code,
                'result': error_result,
                'timestamp': datetime.now().isoformat(),
                'duration': time.time() - start_time
            }
            self.execution_history.append(execution_record)
            
            return error_result
    
    def _execute_with_monitoring(self, code_file: Path, timeout: int) -> Dict:
        """Execute code with monitoring"""
        try:
            # Start process
            process = subprocess.Popen(
                [sys.executable, str(code_file)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=code_file.parent,
                preexec_fn=self._set_process_limits
            )
            
            # Start monitoring
            self.monitor.start_monitoring(process.pid)
            
            try:
                stdout, stderr = process.communicate(timeout=timeout)
                return_code = process.returncode
                
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                return_code = -1
                
            finally:
                self.monitor.stop_monitoring()
            
            # Check for violations
            report = self.monitor.get_report()
            if report['has_violations']:
                return {
                    'success': False,
                    'error': 'Security or resource violations detected',
                    'violations': report['violations'],
                    'stdout': stdout,
                    'stderr': stderr,
                    'return_code': return_code
                }
            
            return {
                'success': return_code == 0,
                'stdout': stdout,
                'stderr': stderr,
                'return_code': return_code,
                'monitoring_report': report
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'traceback': traceback.format_exc()
            }
    
    def _set_process_limits(self):
        """Set process resource limits"""
        try:
            # Set CPU time limit
            resource.setrlimit(resource.RLIMIT_CPU, (self.config.max_cpu_time, self.config.max_cpu_time))
            
            # Set memory limit
            resource.setrlimit(resource.RLIMIT_AS, (self.config.max_memory, self.config.max_memory))
            
            # Set file descriptor limit
            resource.setrlimit(resource.RLIMIT_NOFILE, (100, 100))
            
            # Set core dump size to 0
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            
        except Exception as e:
            logger.error(f"Error setting process limits: {e}")
    
    def execute_in_docker(self, code: str, image: str = "python:3.9-slim", timeout: int = 30) -> Dict:
        """Execute code in Docker container"""
        try:
            client = docker.from_env()
            
            # Create container
            container = client.containers.run(
                image,
                command=f"python -c '{code.replace(chr(39), chr(39) + chr(39) + chr(39))}'",
                detach=True,
                mem_limit=f"{self.config.max_memory // (1024*1024)}m",
                cpu_period=100000,
                cpu_quota=int(100000 * 0.5),  # 50% CPU limit
                network_disabled=True,
                read_only=True,
                tmpfs={'/tmp': 'size=100m'},
                remove=True
            )
            
            try:
                # Wait for completion
                result = container.wait(timeout=timeout)
                
                # Get logs
                logs = container.logs().decode('utf-8')
                
                return {
                    'success': result['StatusCode'] == 0,
                    'stdout': logs,
                    'stderr': '',
                    'return_code': result['StatusCode'],
                    'container_id': container.id
                }
                
            finally:
                try:
                    container.remove(force=True)
                except:
                    pass
                    
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'traceback': traceback.format_exc()
            }
    
    def get_execution_history(self, limit: int = 100) -> List[Dict]:
        """Get execution history"""
        return self.execution_history[-limit:]
    
    def clear_history(self):
        """Clear execution history"""
        self.execution_history.clear()
    
    def get_statistics(self) -> Dict:
        """Get sandbox statistics"""
        total_executions = len(self.execution_history)
        successful_executions = len([e for e in self.execution_history if e['result'].get('success', False)])
        failed_executions = total_executions - successful_executions
        
        # Calculate average duration
        durations = [e['duration'] for e in self.execution_history]
        avg_duration = sum(durations) / len(durations) if durations else 0
        
        return {
            'total_executions': total_executions,
            'successful_executions': successful_executions,
            'failed_executions': failed_executions,
            'success_rate': successful_executions / total_executions if total_executions > 0 else 0,
            'average_duration': avg_duration,
            'last_execution': self.execution_history[-1]['timestamp'] if self.execution_history else None
        }

# Global sandbox instance
sandbox = AdvancedSandbox()

# Utility functions for easy access
def execute_code(code: str, timeout: int = 30, use_docker: bool = False) -> Dict:
    """Execute code in sandbox"""
    if use_docker:
        return sandbox.execute_in_docker(code, timeout=timeout)
    else:
        return sandbox.execute_python(code, timeout=timeout)

def validate_code(code: str) -> Tuple[bool, List[str]]:
    """Validate code for security"""
    return sandbox.validator.validate_code(code)

def get_sandbox_stats() -> Dict:
    """Get sandbox statistics"""
    return sandbox.get_statistics()