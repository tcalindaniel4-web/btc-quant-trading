"""
Controlul boților live din platformă: pornire / oprire / un ciclu / resetare / log.

Fiecare bot rulează ca PROCES SEPARAT (același script ca din consolă), cu ieșirea scrisă în
backend/logs/<bot>.log. Astfel boții continuă să ruleze chiar dacă închizi pagina web, iar
platforma doar îi pornește, îi oprește și le citește log-ul și starea.
"""
import json
import os
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

API_DIR = Path(__file__).resolve().parent
BACKEND_DIR = API_DIR.parent
PROIECT_DIR = BACKEND_DIR.parent
LOG_DIR = BACKEND_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)

BOTI = {
    'sdca': {
        'nume': 'SDCA v2',
        'script': BACKEND_DIR / 'strategii' / 'sdca' / 'bot_live_hedgefound.py',
        'stari': [BACKEND_DIR / 'strategii' / 'sdca' / 'bot_state.json'],
        'interval_implicit': 3.0,       # ore
        'unitate_interval': 'ore',
    },
    'ai': {
        'nume': 'AI Hedge Fund',
        'script': BACKEND_DIR / 'strategii' / 'ai_hedgefund' / 'bot_live_ai.py',
        'stari': [BACKEND_DIR / 'strategii' / 'ai_hedgefund' / 'stare_live.json',
                  BACKEND_DIR / 'strategii' / 'ai_hedgefund' / 'rezultate' / 'jurnal_live.csv'],
        'interval_implicit': 15.0,      # minute
        'unitate_interval': 'minute',
    },
}

_cicluri_in_curs = set()
_lock = threading.Lock()


def _fisier_pid(bot):
    return LOG_DIR / f'{bot}.proces.json'


def _fisier_log(bot):
    return LOG_DIR / f'{bot}.log'


def _activ(pid):
    """True dacă procesul cu acest PID încă rulează."""
    if not pid:
        return False
    if os.name == 'nt':
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        cod = ctypes.c_ulong()
        k.GetExitCodeProcess(h, ctypes.byref(cod))
        k.CloseHandle(h)
        return cod.value == 259  # STILL_ACTIVE
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def _info_proces(bot):
    p = _fisier_pid(bot)
    if not p.exists():
        return None
    try:
        info = json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return None
    if not _activ(info.get('pid')):
        p.unlink(missing_ok=True)
        return None
    return info


def _scrie_log(bot, text):
    with open(_fisier_log(bot), 'a', encoding='utf-8') as f:
        f.write(f"\n[PLATFORMĂ {datetime.now():%Y-%m-%d %H:%M:%S}] {text}\n")


def _lanseaza(bot, argumente):
    cfg = BOTI[bot]
    log = open(_fisier_log(bot), 'a', encoding='utf-8')
    flags = 0
    if os.name == 'nt':
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    return subprocess.Popen([sys.executable, '-u', str(cfg['script'])] + argumente,
                            stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                            cwd=str(PROIECT_DIR), creationflags=flags,
                            env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})


def status(bot):
    cfg = BOTI[bot]
    info = _info_proces(bot)
    return {'bot': bot, 'nume': cfg['nume'], 'ruleaza': info is not None, 'proces': info,
            'ciclu_in_curs': bot in _cicluri_in_curs, 'initializat': cfg['stari'][0].exists(),
            'interval_implicit': cfg['interval_implicit'], 'unitate_interval': cfg['unitate_interval']}


def porneste(bot, capital=None, interval=None):
    with _lock:
        if _info_proces(bot):
            raise ValueError(f"{BOTI[bot]['nume']} rulează deja.")
        if bot in _cicluri_in_curs:
            raise ValueError("Un ciclu manual e în curs. Așteaptă să se termine.")
        cfg = BOTI[bot]
        interval = float(interval or cfg['interval_implicit'])
        argumente = ['--ore', str(interval)] if bot == 'sdca' else ['--interval', str(interval)]
        if capital:
            argumente += ['--capital', str(float(capital))]
        _scrie_log(bot, f"Pornire {cfg['nume']} (ciclu la {interval:g} {cfg['unitate_interval']}"
                        + (f", capital nou ${float(capital):,.0f}" if capital and not cfg['stari'][0].exists() else '') + ")")
        proc = _lanseaza(bot, argumente)
        info = {'pid': proc.pid, 'pornit_la': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'interval': interval, 'unitate': cfg['unitate_interval']}
        _fisier_pid(bot).write_text(json.dumps(info), encoding='utf-8')
        return status(bot)


def opreste(bot):
    with _lock:
        info = _info_proces(bot)
        if not info:
            raise ValueError(f"{BOTI[bot]['nume']} nu rulează.")
        if os.name == 'nt':
            # /T oprește și procesele copil (ex. pipeline-ul de date pornit de botul SDCA)
            subprocess.run(['taskkill', '/PID', str(info['pid']), '/T', '/F'], capture_output=True)
        else:
            os.kill(int(info['pid']), 15)
        _fisier_pid(bot).unlink(missing_ok=True)
        _scrie_log(bot, f"{BOTI[bot]['nume']} oprit din platformă. Starea portofoliului rămâne salvată.")
        return status(bot)


def ciclu(bot, capital=None):
    """Rulează UN ciclu (date noi + decizie) în fundal; rezultatul apare în log."""
    with _lock:
        if _info_proces(bot):
            raise ValueError(f"{BOTI[bot]['nume']} rulează deja în mod autonom; ciclurile vin automat.")
        if bot in _cicluri_in_curs:
            raise ValueError("Un ciclu e deja în curs.")
        _cicluri_in_curs.add(bot)

    def _ruleaza():
        try:
            _scrie_log(bot, "Ciclu manual pornit din platformă.")
            argumente = ['--o-data'] + (['--capital', str(float(capital))] if capital else [])
            _lanseaza(bot, argumente).wait(timeout=900)
        except Exception as e:
            _scrie_log(bot, f"Eroare la ciclul manual: {e}")
        finally:
            _cicluri_in_curs.discard(bot)

    threading.Thread(target=_ruleaza, daemon=True).start()
    return status(bot)


def reseteaza(bot):
    """Arhivează (nu șterge) portofoliul virtual: următoarea pornire începe un portofoliu nou."""
    with _lock:
        if _info_proces(bot) or bot in _cicluri_in_curs:
            raise ValueError("Oprește botul înainte de resetare.")
        arhivate = []
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        for f in BOTI[bot]['stari']:
            if f.exists():
                nou = f.with_name(f"{f.stem}_arhivat_{stamp}{f.suffix}")
                f.rename(nou)
                arhivate.append(nou.name)
        _scrie_log(bot, f"Portofoliu resetat. Arhivat: {', '.join(arhivate) or 'nimic de arhivat'}")
        return {'arhivate': arhivate, **status(bot)}


def log(bot, linii=200):
    p = _fisier_log(bot)
    if not p.exists():
        return []
    with open(p, encoding='utf-8', errors='replace') as f:
        return [l.rstrip('\n') for l in f.readlines()[-linii:]]
