import sys
import os
import asyncio
import platform
import warnings
import gc
import argparse

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


def parse_args():
    parser = argparse.ArgumentParser(description="Ascend Media RPC")
    parser.add_argument(
        "--headless",
        action="store_true",
        default=False,
        help="Run in headless mode (no GUI, Flask API only)",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config.json file",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Dashboard port (overrides config)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="ADB host address (overrides config)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    try:
        args = parse_args()
        setup_logging()

        # Set headless mode via environment variable
        if args.headless or os.environ.get("HEADLESS", "").strip() == "1":
            os.environ["HEADLESS"] = "1"
            os.environ["GUI_MODE"] = "browser"

        # Override config path if specified
        if args.config:
            os.environ["ASCEND_CONFIG_PATH"] = args.config

        # Pass CLI overrides via environment
        if args.port:
            os.environ["ASCEND_PORT"] = str(args.port)
        if args.host:
            os.environ["ASCEND_ADB_HOST"] = args.host

        app = App()

    except KeyboardInterrupt:
        pass

    except Exception:
        import traceback
        traceback.print_exc()
        if not os.environ.get("HEADLESS"):
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
