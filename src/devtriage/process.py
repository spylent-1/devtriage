import asyncio
import os
import shutil
from pathlib import Path


def executable(name):
    found = shutil.which(name)
    if not found and name == "docker":
        for root in (Path(os.getenv("LOCALAPPDATA", ""))/"Programs/DockerDesktop", Path("C:/Program Files/Docker/Docker")):
            candidate = root / "resources/bin/docker.exe"
            if candidate.is_file():
                return str(candidate)
    return found


async def run(args: list[str], cwd=None, timeout=30) -> dict:
    args = [executable(args[0]) or args[0], *args[1:]]
    env = os.environ.copy()
    env["PATH"] = str(Path(args[0]).parent) + os.pathsep + env.get("PATH", "")
    proc = await asyncio.create_subprocess_exec(*args, cwd=cwd, env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    output = bytearray()
    async def drain():
        while chunk := await proc.stdout.read(8192):
            if len(output) < 100000:
                output.extend(chunk[:100000-len(output)])
        await proc.wait()
    try:
        await asyncio.wait_for(drain(), timeout)
    except (TimeoutError, asyncio.CancelledError):
        proc.kill()
        await proc.wait()
        raise
    return {"returncode": proc.returncode, "output": output.decode("utf-8", errors="replace")}
