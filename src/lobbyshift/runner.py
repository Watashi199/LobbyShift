"""Async subprocess runner.

Every system command goes through a ``Runner`` so tests can substitute a fake
that records argv lists instead of touching the host network stack.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Protocol

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Result:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class CommandError(RuntimeError):
    def __init__(self, argv: tuple[str, ...], result: Result):
        self.argv = argv
        self.result = result
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        super().__init__(f"`{' '.join(argv)}` failed: {detail}")


class Runner(Protocol):
    async def run(self, *argv: str, input: str | None = None, check: bool = True) -> Result: ...


class SubprocessRunner:
    def __init__(self, timeout: float = 20.0):
        self.timeout = timeout

    async def run(self, *argv: str, input: str | None = None, check: bool = True) -> Result:
        log.debug("exec: %s", " ".join(argv))
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.PIPE if input is not None else asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            result = Result(127, "", f"{argv[0]}: command not found")
        else:
            try:
                out, err = await asyncio.wait_for(
                    proc.communicate(input.encode() if input is not None else None),
                    timeout=self.timeout,
                )
            except (BrokenPipeError, ConnectionResetError, RuntimeError):
                # The child exited before reading its stdin (uvloop raises
                # RuntimeError for a closed transport). Report its real error.
                out = await proc.stdout.read() if proc.stdout else b""
                err = await proc.stderr.read() if proc.stderr else b""
                await proc.wait()
            except TimeoutError:
                proc.kill()
                await proc.wait()
                result = Result(124, "", f"timed out after {self.timeout}s")
            else:
                result = Result(
                    proc.returncode or 0,
                    out.decode(errors="replace"),
                    err.decode(errors="replace"),
                )
        if check and not result.ok:
            raise CommandError(tuple(argv), result)
        return result
