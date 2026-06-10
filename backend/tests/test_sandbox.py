"""测试 ProcessSandbox 进程沙箱的正常执行、超时和安全拦截功能。"""

import json

from assef.sandbox import ProcessSandbox
from assef.models import SandboxResult

ECHO_CODE = '''
import json, sys
data = json.loads(sys.stdin.read())
print(json.dumps(data))
'''

QUERY_CODE = '''
import json, sys
data = json.loads(sys.stdin.read())
name = data.get("name", "")
print(json.dumps({"result": name}))
'''

INFINITE_LOOP_CODE = '''
while True:
    pass
'''

OS_SYSTEM_CODE = '''
import os
os.system("echo hello")
'''

SUBPROCESS_CODE = '''
import subprocess
subprocess.run(["echo", "hello"])
'''

DYNAMIC_IMPORT_CODE = '''
os = __import__("os")
print(os.getcwd())
'''


class TestProcessSandboxNormal:
    def test_normal_execution_returns_stdout(self):
        sb = ProcessSandbox()
        result = sb.execute(ECHO_CODE, {"hello": "world"})
        assert result.exit_code == 0
        assert result.timed_out == False
        assert "hello" in result.stdout
        assert result.elapsed_seconds >= 0

    def test_stdin_passed_correctly(self):
        sb = ProcessSandbox()
        result = sb.execute(QUERY_CODE, {"name": "alice"})
        assert result.exit_code == 0
        parsed = json.loads(result.stdout)
        assert parsed["result"] == "alice"

    def test_elapsed_time_is_recorded(self):
        sb = ProcessSandbox()
        result = sb.execute(ECHO_CODE, {"test": 1})
        assert result.elapsed_seconds > 0


class TestProcessSandboxTimeout:
    """测试沙箱超时终止：无限循环被中断。"""

    def test_infinite_loop_is_terminated(self):
        sb = ProcessSandbox()
        result = sb.execute(INFINITE_LOOP_CODE, {}, timeout=2.0)
        assert result.timed_out == True
        assert result.exit_code == -1


class TestProcessSandboxSecurity:
    """测试沙箱安全拦截：os.system、subprocess、动态导入、eval/exec、文件打开等被阻止。"""

    def test_os_system_blocked(self):
        sb = ProcessSandbox()
        result = sb.execute(OS_SYSTEM_CODE, {})
        assert result.exit_code == -1
        assert "SecurityError" in result.stderr

    def test_subprocess_blocked(self):
        sb = ProcessSandbox()
        result = sb.execute(SUBPROCESS_CODE, {})
        assert result.exit_code == -1
        assert "SecurityError" in result.stderr

    def test_dynamic_import_blocked(self):
        sb = ProcessSandbox()
        result = sb.execute(DYNAMIC_IMPORT_CODE, {})
        assert result.exit_code == -1
        assert "SecurityError" in result.stderr

    def test_eval_blocked(self):
        sb = ProcessSandbox()
        result = sb.execute('eval("1+1")', {})
        assert result.exit_code == -1
        assert "SecurityError" in result.stderr

    def test_exec_blocked(self):
        sb = ProcessSandbox()
        result = sb.execute('exec("x=1")', {})
        assert result.exit_code == -1
        assert "SecurityError" in result.stderr

    def test_file_open_blocked(self):
        sb = ProcessSandbox()
        result = sb.execute('open("test.txt", "w")', {})
        assert result.exit_code == -1
        assert "SecurityError" in result.stderr
