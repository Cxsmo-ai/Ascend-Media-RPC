import sys
import os
import asyncio
import platform
import warnings
import gc

def install_windows_asyncio_pipe_fix():
    """
    Stops Windows asyncio Proactor cleanup spam:

    Exception ignored in: _ProactorBasePipeTransport.__del__
    ValueError: I/O operation on closed pipe

    This does NOT hide real crashes. It only suppresses this known shutdown noise.
    """
    if platform.system() != "Windows":
        return

    warnings.filterwarnings("ignore", category=ResourceWarning)

    original_unraisablehook = sys.unraisablehook

    def quiet_unraisablehook(unraisable):
        exc = unraisable.exc_value
        obj = unraisable.object

        module = getattr(obj, "__module__", "") or ""
        qualname = getattr(obj, "__qualname__", "") or getattr(obj, "__name__", "") or ""
        obj_name = f"{module}.{qualname}"

        if (
            isinstance(exc, ValueError)
            and "I/O operation on closed pipe" in str(exc)
            and (
                "asyncio.proactor_events" in obj_name
                or "_ProactorBasePipeTransport.__del__" in obj_name
            )
        ):
            return

        original_unraisablehook(unraisable)

    sys.unraisablehook = quiet_unraisablehook


install_windows_asyncio_pipe_fix()

from src.gui.app import App
from src.core.logger import setup_logging

if __name__ == "__main__":
    try:
        setup_logging()
        app = App()

    except KeyboardInterrupt:
        pass

    except Exception:
        import traceback
        traceback.print_exc()
        input("Critical Crash. Press Enter...")

    finally:
        # Give asyncio transports a tiny chance to finish cleanup before Python exits.
        if platform.system() == "Windows":
            try:
                loop = asyncio.get_event_loop()
                if not loop.is_closed():
                    loop.run_until_complete(asyncio.sleep(0.05))
            except Exception:
                pass

            try:
                gc.collect()
            except Exception:
                pass
