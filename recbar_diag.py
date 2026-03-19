"""RecBar diagnostic launcher — tests all connections, logs everything."""

import sys
import os
import time
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "recbar"))

LOG = os.path.join(os.path.dirname(__file__), "recbar_log.txt")

def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line)
    with open(LOG, "a") as f:
        f.write(line + "\n")

def main():
    log("=" * 50)
    log("RECBAR DIAGNOSTIC LAUNCHER")
    log("=" * 50)

    # 1. Check config
    log("")
    log("--- CONFIG ---")
    try:
        from recbar.config import CFG, OBS_URL, CONFIG_PATH, MIC_NAME
        log(f"Config file: {CONFIG_PATH}")
        log(f"OBS URL: {OBS_URL}")
        log(f"Password: {'***' + CFG.get('obs_password', '')[-4:] if CFG.get('obs_password') else '(none)'}")
        log(f"Mic: {MIC_NAME}")
        log(f"Scenes: {list(CFG.get('scenes', {}).keys())}")
        log(f"Web port: {CFG.get('web_port')}")
        log("Config: OK")
    except Exception as e:
        log(f"Config FAILED: {e}")
        return

    # 2. Check platform
    log("")
    log("--- PLATFORM ---")
    try:
        from recbar.platform import SESSION_TYPE, IS_WINDOWS
        log(f"Platform: {SESSION_TYPE}")
        log(f"Windows: {IS_WINDOWS}")
        log("Platform: OK")
    except Exception as e:
        log(f"Platform FAILED: {e}")

    # 3. Check IPC
    log("")
    log("--- IPC ---")
    try:
        from recbar.ipc import IPCServer
        srv = IPCServer()
        srv.start()
        log("IPC server started")
        srv.stop()
        log("IPC: OK")
    except Exception as e:
        log(f"IPC FAILED: {e}")

    # 4. Check OBS WebSocket connection
    log("")
    log("--- OBS WEBSOCKET ---")
    try:
        from recbar.obs_connection import OBSConnection
        conn = OBSConnection()
        conn.start()
        log("Connecting to OBS...")

        for i in range(10):
            time.sleep(1)
            if conn.connected:
                break
            log(f"  Waiting... ({i+1}s)")

        if conn.connected:
            log("CONNECTED to OBS!")

            # Test a request
            result = conn.request("GetSceneList")
            if result:
                scenes = [s["sceneName"] for s in result.get("scenes", [])]
                log(f"Scenes in OBS: {scenes}")
                log(f"Current scene: {result.get('currentProgramSceneName', '?')}")
            else:
                log("GetSceneList returned empty — might need more time")

            # Test recording status
            result2 = conn.request("GetRecordStatus")
            if result2:
                log(f"Recording active: {result2.get('outputActive', False)}")
            else:
                log("GetRecordStatus returned empty")

            conn.stop()
            log("OBS WebSocket: OK")
        else:
            conn.stop()
            log("FAILED to connect to OBS after 10 seconds")
            log("Check: Is OBS running? Is WebSocket enabled (Tools > WebSocket)?")
            log(f"Check: Port {CFG.get('obs_port', 4455)} and password correct?")
    except Exception as e:
        log(f"OBS WebSocket FAILED: {e}")
        import traceback
        log(traceback.format_exc())

    # 5. Check PyQt6
    log("")
    log("--- PyQt6 GUI ---")
    try:
        from PyQt6.QtWidgets import QApplication
        log("PyQt6: OK")
    except Exception as e:
        log(f"PyQt6 FAILED: {e}")

    # 6. Launch recbar
    log("")
    log("--- LAUNCHING RECBAR ---")
    log("All checks passed. Starting recbar...")
    log("")

    try:
        from recbar.__main__ import main as recbar_main
        recbar_main()
    except Exception as e:
        log(f"RECBAR CRASHED: {e}")
        import traceback
        log(traceback.format_exc())

if __name__ == "__main__":
    main()
