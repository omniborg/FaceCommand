"""
FaceCommand - Native Desktop App
============================================
Single-file native app. No browser needed.
Uses SendInput with hardware scan codes (game-compatible).

Requirements: pip install PyQt6 opencv-python mediapipe numpy
"""

import sys, os, json, math, time, subprocess, threading, ctypes
from ctypes import wintypes
from datetime import datetime
from collections import deque

_missing = []
try: import cv2
except ImportError: _missing.append("opencv-python")
try: import mediapipe as mp
except ImportError: _missing.append("mediapipe")
try: import numpy as np
except ImportError: _missing.append("numpy")
try:
    from PyQt6.QtWidgets import *
    from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot, QMutex, QMutexLocker
    from PyQt6.QtGui import QImage, QPixmap, QKeySequence
except ImportError: _missing.append("PyQt6")

if _missing:
    print(f"Missing: pip install {' '.join(_missing)}")
    input("Press Enter..."); sys.exit(1)

user32 = ctypes.windll.user32
INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
KEYEVENTF_SCANCODE, KEYEVENTF_KEYUP, KEYEVENTF_EXTENDEDKEY = 0x0008, 0x0002, 0x0001
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP = 0x0008, 0x0010
MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP = 0x0020, 0x0040
MOUSEEVENTF_WHEEL = 0x0800
WHEEL_DELTA = 120

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx",ctypes.c_long),("dy",ctypes.c_long),("mouseData",ctypes.c_ulong),
                ("dwFlags",ctypes.c_ulong),("time",ctypes.c_ulong),("dwExtraInfo",ctypes.POINTER(ctypes.c_ulong))]
class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk",ctypes.c_ushort),("wScan",ctypes.c_ushort),("dwFlags",ctypes.c_ulong),
                ("time",ctypes.c_ulong),("dwExtraInfo",ctypes.POINTER(ctypes.c_ulong))]
class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi",MOUSEINPUT),("ki",KEYBDINPUT)]
class INPUT(ctypes.Structure):
    _fields_ = [("type",ctypes.c_ulong),("union",INPUT_UNION)]

def send_input(*inputs):
    n = len(inputs); arr = (INPUT * n)(*inputs)
    user32.SendInput(n, arr, ctypes.sizeof(INPUT))

VK_CODES = {
    'a':0x41,'b':0x42,'c':0x43,'d':0x44,'e':0x45,'f':0x46,'g':0x47,'h':0x48,'i':0x49,'j':0x4A,
    'k':0x4B,'l':0x4C,'m':0x4D,'n':0x4E,'o':0x4F,'p':0x50,'q':0x51,'r':0x52,'s':0x53,'t':0x54,
    'u':0x55,'v':0x56,'w':0x57,'x':0x58,'y':0x59,'z':0x5A,
    '0':0x30,'1':0x31,'2':0x32,'3':0x33,'4':0x34,'5':0x35,'6':0x36,'7':0x37,'8':0x38,'9':0x39,
    'f1':0x70,'f2':0x71,'f3':0x72,'f4':0x73,'f5':0x74,'f6':0x75,'f7':0x76,'f8':0x77,
    'f9':0x78,'f10':0x79,'f11':0x7A,'f12':0x7B,
    'enter':0x0D,'return':0x0D,'tab':0x09,'space':0x20,' ':0x20,'backspace':0x08,'delete':0x2E,
    'escape':0x1B,'esc':0x1B,'up':0x26,'arrowup':0x26,'down':0x28,'arrowdown':0x28,
    'left':0x25,'arrowleft':0x25,'right':0x27,'arrowright':0x27,
    'home':0x24,'end':0x23,'pageup':0x21,'page_up':0x21,'pagedown':0x22,'page_down':0x22,
    'insert':0x2D,'capslock':0x14,'numlock':0x90,'printscreen':0x2C,'scrolllock':0x91,
    'pause':0x13,'menu':0x5D,'-':0xBD,'=':0xBB,'[':0xDB,']':0xDD,
    '\\':0xDC,';':0xBA,"'":0xDE,',':0xBC,'.':0xBE,'/':0xBF,'`':0xC0,
}
EXTENDED_VK = {0x25,0x26,0x27,0x28,0x2D,0x2E,0x24,0x23,0x21,0x22,0x90,0x2C,0x5D}
MODIFIER_VK = {'ctrl':0xA2,'control':0xA2,'alt':0xA4,'shift':0xA0,
               'meta':0x5B,'win':0x5B,'windows':0x5B,'cmd':0x5B,'super':0x5B}

def make_key_input(vk, key_up=False):
    scan = user32.MapVirtualKeyW(vk, 0)
    flags = KEYEVENTF_SCANCODE
    if vk in EXTENDED_VK: flags |= KEYEVENTF_EXTENDEDKEY
    if key_up: flags |= KEYEVENTF_KEYUP
    inp = INPUT(); inp.type = INPUT_KEYBOARD
    inp.union.ki.wVk = 0; inp.union.ki.wScan = scan; inp.union.ki.dwFlags = flags
    inp.union.ki.time = 0; inp.union.ki.dwExtraInfo = ctypes.pointer(ctypes.c_ulong(0))
    return inp

def make_mouse_input(flags, mouse_data=0):
    inp = INPUT(); inp.type = INPUT_MOUSE
    inp.union.mi.dx = 0; inp.union.mi.dy = 0; inp.union.mi.mouseData = mouse_data
    inp.union.mi.dwFlags = flags; inp.union.mi.time = 0
    inp.union.mi.dwExtraInfo = ctypes.pointer(ctypes.c_ulong(0))
    return inp

def parse_key(key_str):
    parts = key_str.split('+'); key_part = parts[-1].strip()
    mods = [MODIFIER_VK[p.strip().lower()] for p in parts[:-1] if p.strip().lower() in MODIFIER_VK]
    kl = key_part.lower()
    vk = VK_CODES.get(kl, 0)
    if vk == 0 and len(key_part) == 1:
        vk = VK_CODES.get(key_part.lower(), 0)
        if vk == 0: vk = user32.VkKeyScanW(ord(key_part)) & 0xFF
    return mods, vk

def execute_key_press(key_bind):
    if not key_bind: return
    mods, vk = parse_key(key_bind)
    if vk == 0: return
    for m in mods: send_input(make_key_input(m))
    send_input(make_key_input(vk))
    time.sleep(0.05)
    send_input(make_key_input(vk, True))
    for m in reversed(mods): send_input(make_key_input(m, True))

_drag_active = False
def execute_mouse_action(t):
    global _drag_active
    if t == 'left_click': send_input(make_mouse_input(MOUSEEVENTF_LEFTDOWN), make_mouse_input(MOUSEEVENTF_LEFTUP))
    elif t == 'right_click': send_input(make_mouse_input(MOUSEEVENTF_RIGHTDOWN), make_mouse_input(MOUSEEVENTF_RIGHTUP))
    elif t == 'double_click': send_input(make_mouse_input(MOUSEEVENTF_LEFTDOWN), make_mouse_input(MOUSEEVENTF_LEFTUP), make_mouse_input(MOUSEEVENTF_LEFTDOWN), make_mouse_input(MOUSEEVENTF_LEFTUP))
    elif t == 'middle_click': send_input(make_mouse_input(MOUSEEVENTF_MIDDLEDOWN), make_mouse_input(MOUSEEVENTF_MIDDLEUP))
    elif t == 'scroll_up': send_input(make_mouse_input(MOUSEEVENTF_WHEEL, WHEEL_DELTA * 3))
    elif t == 'scroll_down': send_input(make_mouse_input(MOUSEEVENTF_WHEEL, ctypes.c_ulong(-WHEEL_DELTA * 3).value))
    elif t == 'drag_toggle':
        if _drag_active: send_input(make_mouse_input(MOUSEEVENTF_LEFTUP)); _drag_active = False
        else: send_input(make_mouse_input(MOUSEEVENTF_LEFTDOWN)); _drag_active = True

def execute_key_down(key_bind):
    """Press key(s) down and hold them."""
    if not key_bind: return
    mods, vk = parse_key(key_bind)
    if vk == 0: return
    for m in mods: send_input(make_key_input(m))
    send_input(make_key_input(vk))

def execute_key_up(key_bind):
    """Release held key(s)."""
    if not key_bind: return
    mods, vk = parse_key(key_bind)
    if vk == 0: return
    send_input(make_key_input(vk, True))
    for m in reversed(mods): send_input(make_key_input(m, True))

_MOUSE_DOWN_FLAGS = {
    'left_click': MOUSEEVENTF_LEFTDOWN, 'right_click': MOUSEEVENTF_RIGHTDOWN,
    'middle_click': MOUSEEVENTF_MIDDLEDOWN,
}
_MOUSE_UP_FLAGS = {
    'left_click': MOUSEEVENTF_LEFTUP, 'right_click': MOUSEEVENTF_RIGHTUP,
    'middle_click': MOUSEEVENTF_MIDDLEUP,
}

def execute_mouse_down(action_type):
    """Press mouse button down (for hold/toggle modes)."""
    f = _MOUSE_DOWN_FLAGS.get(action_type)
    if f: send_input(make_mouse_input(f))

def execute_mouse_up(action_type):
    """Release mouse button (for hold/toggle modes)."""
    f = _MOUSE_UP_FLAGS.get(action_type)
    if f: send_input(make_mouse_input(f))

def execute_hold_start(action_type, key_bind=''):
    """Start a sustained hold (key down or mouse down)."""
    if action_type == 'key': execute_key_down(key_bind)
    elif action_type in _MOUSE_DOWN_FLAGS: execute_mouse_down(action_type)

def execute_hold_stop(action_type, key_bind=''):
    """Release a sustained hold."""
    if action_type == 'key': execute_key_up(key_bind)
    elif action_type in _MOUSE_UP_FLAGS: execute_mouse_up(action_type)

def parse_macro(macro_str):
    """Parse macro string into list of steps.
    Format: step;step;step  (semicolon-separated)
    Steps:
      key:W           - press and release key W
      key:Ctrl+C      - press and release Ctrl+C
      hold:W:500      - hold key W for 500ms
      mouse:left_click - left click
      mouse:scroll_up  - scroll up
      delay:100        - wait 100ms
    """
    steps = []
    for part in macro_str.split(';'):
        part = part.strip()
        if not part: continue
        if part.startswith('key:'):
            steps.append(('key', part[4:].strip()))
        elif part.startswith('hold:'):
            # hold:key:duration_ms
            rest = part[5:]
            pieces = rest.rsplit(':', 1)
            if len(pieces) == 2:
                try: steps.append(('hold', pieces[0].strip(), int(pieces[1].strip())))
                except ValueError: pass
            else:
                steps.append(('key', rest.strip()))
        elif part.startswith('mouse:'):
            steps.append(('mouse', part[6:].strip()))
        elif part.startswith('delay:'):
            try: steps.append(('delay', int(part[6:].strip())))
            except ValueError: pass
    return steps

def execute_macro(macro_str):
    """Execute a macro sequence."""
    if not macro_str: return
    steps = parse_macro(macro_str)
    prev_type = None
    for step in steps:
        # Auto-insert 50ms delay between consecutive mouse or key actions
        if prev_type in ('mouse','key') and step[0] in ('mouse','key'):
            time.sleep(0.05)
        if step[0] == 'key':
            execute_key_press(step[1])
        elif step[0] == 'mouse':
            execute_mouse_action(step[1])
        elif step[0] == 'delay':
            time.sleep(step[1] / 1000.0)
        elif step[0] == 'hold':
            mods, vk = parse_key(step[1])
            if vk:
                for m in mods: send_input(make_key_input(m))
                send_input(make_key_input(vk))
                time.sleep(step[2] / 1000.0)
                send_input(make_key_input(vk, True))
                for m in reversed(mods): send_input(make_key_input(m, True))
        prev_type = step[0]

def execute_action(action_type, key_bind='', command='', macro=''):
    """Execute a single-fire action (original behavior + macro support)."""
    if not action_type or action_type == 'none': return
    if action_type == 'key': execute_key_press(key_bind)
    elif action_type == 'macro': execute_macro(macro)
    elif action_type == 'the_rock': play_sound_file('the_rock.mp3')
    elif action_type == 'command' and command:
        try: subprocess.Popen(command, shell=True)
        except: pass
    else: execute_mouse_action(action_type)

def play_sound_file(filename):
    """Play an MP3/WAV file using PowerShell MediaPlayer (reliable on all Windows)."""
    fpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    print(f"[SOUND] Attempting to play: {fpath}")
    if not os.path.exists(fpath):
        print(f"[SOUND] ERROR: File not found: {fpath}")
        return
    print(f"[SOUND] File exists, size: {os.path.getsize(fpath)} bytes")
    fpath_ps = fpath.replace("'", "''")
    ps_cmd = (
        f"try {{"
        f"  Add-Type -AssemblyName PresentationCore;"
        f"  $p=New-Object System.Windows.Media.MediaPlayer;"
        f"  $p.Open([Uri]'{fpath_ps}');"
        f"  Start-Sleep -Milliseconds 500;"
        f"  $p.Play();"
        f"  Start-Sleep -Seconds 10;"
        f"  $p.Close()"
        f"}} catch {{"
        f"  $_ | Out-File -FilePath '{fpath_ps}.error.log'"
        f"}}"
    )
    cmd = ['powershell', '-WindowStyle', 'Hidden', '-Command', ps_cmd]
    print(f"[SOUND] Running: {' '.join(cmd[:3])}...")
    try:
        proc = subprocess.Popen(cmd, creationflags=0x08000000,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(f"[SOUND] PowerShell PID: {proc.pid}")
        # Check result in background
        def _check():
            out, err = proc.communicate(timeout=15)
            if proc.returncode != 0:
                print(f"[SOUND] PowerShell exited with code {proc.returncode}")
                if err: print(f"[SOUND] stderr: {err.decode('utf-8','replace')}")
                if out: print(f"[SOUND] stdout: {out.decode('utf-8','replace')}")
            else:
                print(f"[SOUND] PowerShell completed OK")
        threading.Thread(target=_check, daemon=True).start()
    except Exception as e:
        print(f"[SOUND] ERROR launching PowerShell: {e}")

# ÃƒÂ¢Ã¢â‚¬Â¢Ã‚ÂÃƒÂ¢Ã¢â‚¬Â¢Ã‚ÂÃƒÂ¢Ã¢â‚¬Â¢Ã‚Â FACE MESH ÃƒÂ¢Ã¢â‚¬Â¢Ã‚ÂÃƒÂ¢Ã¢â‚¬Â¢Ã‚ÂÃƒÂ¢Ã¢â‚¬Â¢Ã‚Â

LEFT_EYE_EAR = [33,160,158,133,153,144]; RIGHT_EYE_EAR = [362,385,387,263,373,380]
LEFT_EYEBROW = [70,63,105,66,107]; RIGHT_EYEBROW = [300,293,334,296,336]
UPPER_LIP=13; LOWER_LIP=14; MOUTH_LEFT=61; MOUTH_RIGHT=291
NOSE_TIP=1; CHIN=152; LEFT_CHEEK=234; RIGHT_CHEEK=454
LEFT_IRIS=468; RIGHT_IRIS=473
LEFT_EYE_TOP=159; LEFT_EYE_BOT=145; LEFT_EYE_IN=133; LEFT_EYE_OUT=33
RIGHT_EYE_TOP=386; RIGHT_EYE_BOT=374; RIGHT_EYE_IN=362; RIGHT_EYE_OUT=263
# Smirk: mouth corner landmarks (Y position difference = asymmetric smile)
MOUTH_CORNER_LEFT = 61; MOUTH_CORNER_RIGHT = 291
# Nose scrunch: use nose wing landmarks that splay outward + upper lip raise
# Landmarks 48/278 are nose wing tips (alae), 129/358 are outer nose creases
# Pucker: mouth width + vertical lip compression only (no Z)
LIP_TOP_OUTER = 0; LIP_BOT_OUTER = 17
LIP_CENTER_UPPER = 0; LIP_CENTER_LOWER = 17; LIP_LEFT = 61; LIP_RIGHT = 291
# Brow furrow
LEFT_BROW_INNER = 107; RIGHT_BROW_INNER = 336
LEFT_INNER_EYE = 133; RIGHT_INNER_EYE = 362

def _dist(a,b): return math.sqrt((a.x-b.x)**2+(a.y-b.y)**2+(getattr(a,'z',0)-getattr(b,'z',0))**2)
def _ear(lm,idx):
    p=[lm[i] for i in idx]; return(_dist(p[1],p[5])+_dist(p[2],p[4]))/(2*_dist(p[0],p[3])+0.0001)

CAL_N = 45

class GestureDetector:
    def __init__(self): self.reset()
    def reset(self): self.cal_n=0; self.cal_s={}; self.bl={}
    @property
    def calibrated(self): return self.cal_n >= CAL_N
    @property
    def cal_pct(self): return int(min(100, self.cal_n/CAL_N*100))

    def compute(self, lm, tilt_comp=35, sens=None):
        """sens: dict of gesture_id -> multiplier. >1 = less motion needed, <1 = more motion needed."""
        if sens is None: sens = {}
        raw = {}
        fw = _dist(lm[LEFT_CHEEK],lm[RIGHT_CHEEK])
        fh = _dist(lm[NOSE_TIP],lm[CHIN])
        le = _ear(lm,LEFT_EYE_EAR); re = _ear(lm,RIGHT_EYE_EAR)

        # Gaze-compensated EAR
        has_iris = len(lm) > RIGHT_IRIS
        if has_iris and self.calibrated:
            leh = _dist(lm[LEFT_EYE_TOP], lm[LEFT_EYE_BOT])
            reh = _dist(lm[RIGHT_EYE_TOP], lm[RIGHT_EYE_BOT])
            if leh > 0.001 and reh > 0.001:
                l_gy = (lm[LEFT_IRIS].y - lm[LEFT_EYE_TOP].y) / (leh + 0.0001)
                r_gy = (lm[RIGHT_IRIS].y - lm[RIGHT_EYE_TOP].y) / (reh + 0.0001)
                COMP = 0.15
                le = le + max(0, l_gy - 0.5) * 2 * COMP
                re = re + max(0, r_gy - 0.5) * 2 * COMP

        raw['blink'] = max(0,min(100,(1-(((le+re)/2)-0.05)/(0.30/sens.get('blink',1.0)))*100))
        log_ratio = math.log((le + 0.001) / (re + 0.001))
        raw['wink_left'] = max(0, min(100, -log_ratio / (0.6/sens.get('wink_left',1.0)) * 100))
        raw['wink_right'] = max(0, min(100, log_ratio / (0.6/sens.get('wink_right',1.0)) * 100))

        hairline = lm[10]
        ref_len = fw + 0.0001
        lby = sum(lm[i].y for i in LEFT_EYEBROW)/5
        rby = sum(lm[i].y for i in RIGHT_EYEBROW)/5
        aby = (lby+rby)/2
        br = (aby - hairline.y) / ref_len
        lbr = (lby - hairline.y) / ref_len
        rbr = (rby - hairline.y) / ref_len

        mo = _dist(lm[UPPER_LIP],lm[LOWER_LIP])/fw  # normalize by face WIDTH, not height (beard-robust)
        sr = _dist(lm[MOUTH_LEFT],lm[MOUTH_RIGHT])/fw

        # Directional lip signals for separating smile from mouth_open:
        # Smile: upper lip rises toward nose + corners rise
        # Mouth open: lower lip drops away from nose
        upper_lip_to_nose = (lm[UPPER_LIP].y - lm[NOSE_TIP].y) / (fw + 0.0001)  # shrinks when smiling
        lower_lip_to_nose = (lm[LOWER_LIP].y - lm[NOSE_TIP].y) / (fw + 0.0001)  # grows when jaw drops
        corner_avg_y = (lm[MOUTH_LEFT].y + lm[MOUTH_RIGHT].y) / 2
        corner_to_nose = (corner_avg_y - lm[NOSE_TIP].y) / (fw + 0.0001)  # shrinks when smiling

        # Pucker: mouth narrows horizontally
        pucker_width = sr  # already normalized mouth width

        # Smirk: asymmetry of mouth corners. Left smirk = left corner higher (lower Y).
        l_corner_y = lm[MOUTH_CORNER_LEFT].y
        r_corner_y = lm[MOUTH_CORNER_RIGHT].y
        # Normalize by face height so head tilt scale doesn't matter
        mouth_asym = (r_corner_y - l_corner_y) / (fh + 0.0001)  # positive = left higher = left smirk

        # Brow furrow: brow-to-eye-corner gap (pitch-robust) + inter-brow gap
        brow_inner_gap = _dist(lm[LEFT_BROW_INNER], lm[RIGHT_BROW_INNER]) / (fw + 0.0001)
        # Use fw (face width) not fh Ã¢â‚¬â€ fh changes when mouth opens (chin drops), causing crosstalk
        l_brow_eye_gap = (lm[LEFT_BROW_INNER].y - lm[LEFT_INNER_EYE].y) / (fw + 0.0001)
        r_brow_eye_gap = (lm[RIGHT_BROW_INNER].y - lm[RIGHT_INNER_EYE].y) / (fw + 0.0001)
        brow_eye_gap = (l_brow_eye_gap + r_brow_eye_gap) / 2

        nose_z = lm[1].z; forehead_z = lm[10].z
        pitch_indicator = forehead_z - nose_z

        if self.cal_n < CAL_N:
            s=self.cal_s
            for k,v in [('br',br),('lbr',lbr),('rbr',rbr),('sr',sr),('mo',mo),
                        ('pitch',pitch_indicator),('pucker_w',pucker_width),
                        ('mouth_asym',mouth_asym),
                        ('ul_nose',upper_lip_to_nose),('ll_nose',lower_lip_to_nose),
                        ('corner_nose',corner_to_nose),
                        ('brow_gap',brow_inner_gap),
                        ('brow_eye_gap',brow_eye_gap)]:
                s[k]=s.get(k,0)+v
            self.cal_n += 1
            if self.cal_n == CAL_N:
                self.bl = {k:v/CAL_N for k,v in s.items()}

        if self.calibrated:
            pitch_dev = pitch_indicator - self.bl['pitch']
            pitch_comp = pitch_dev * -(tilt_comp / 100.0)

            raw_left = max(0,min(100,(self.bl['lbr']-(lbr - pitch_comp))/(0.03/sens.get('eyebrow_raise_left',1.0))*100))
            raw_right = max(0,min(100,(self.bl['rbr']-(rbr - pitch_comp))/(0.03/sens.get('eyebrow_raise_right',1.0))*100))

            both_threshold = 85
            if raw_left >= both_threshold and raw_right >= both_threshold:
                raw['eyebrow_raise'] = max(0,min(100,(self.bl['br']-(br - pitch_comp))/(0.03/sens.get('eyebrow_raise',1.0))*100))
                raw['eyebrow_raise_left'] = 0; raw['eyebrow_raise_right'] = 0
            else:
                raw['eyebrow_raise'] = 0
                raw['eyebrow_raise_left'] = raw_left; raw['eyebrow_raise_right'] = raw_right

            # Smile: corners rise + upper lip rises + mouth widens
            # All three go negative (toward nose) when smiling
            s_sm = sens.get('smile', 1.0)
            corner_rise = (self.bl['corner_nose'] - corner_to_nose) / (0.04/s_sm)
            upper_rise = (self.bl['ul_nose'] - upper_lip_to_nose) / (0.03/s_sm)
            width_inc = (sr - self.bl['sr']) / (0.10/s_sm)
            raw['smile'] = max(0, min(100, (corner_rise*0.40 + upper_rise*0.25 + width_inc*0.35) * 100))

            # Mouth open: lower lip drops away from nose (jaw drops)
            lower_drop = (lower_lip_to_nose - self.bl['ll_nose']) / (0.06/sens.get('mouth_open',1.0))
            raw['mouth_open'] = max(0, min(100, lower_drop * 100))
            # Suppress mouth_open when smiling strongly (smile pulls lower lip slightly)
            if raw['smile'] > 50:
                raw['mouth_open'] = max(0, raw['mouth_open'] - raw['smile'] * 0.3)

            # Pucker: purely mouth width narrowing
            w_shrink = (self.bl['pucker_w'] - pucker_width) / (0.05/sens.get('pucker',1.0))
            raw_pucker = max(0, min(100, w_shrink * 100))
            if raw['smile'] > 40 or raw['mouth_open'] > 40: raw_pucker *= 0.2
            raw['pucker'] = max(0, min(100, raw_pucker))

            # Smirk: mouth corner asymmetry
            asym_dev = mouth_asym - self.bl['mouth_asym']
            raw['smirk_left'] = max(0, min(100, asym_dev / (0.025/sens.get('smirk_left',1.0)) * 100))
            raw['smirk_right'] = max(0, min(100, -asym_dev / (0.025/sens.get('smirk_right',1.0)) * 100))

            # Brow furrow: pitch-robust via brow-to-eye-corner gap
            # Apply pitch compensation: tilting forward shrinks brow_eye_gap artificially
            s_bf = sens.get('brow_furrow', 1.0)
            compensated_brow_eye_gap = brow_eye_gap - pitch_comp * 0.5
            brow_drop = (compensated_brow_eye_gap - self.bl['brow_eye_gap']) / (0.015/s_bf)
            gap_shrink = (self.bl['brow_gap'] - brow_inner_gap) / (0.03/s_bf)
            raw_furrow = max(0, min(100, (brow_drop*0.55 + gap_shrink*0.45) * 100))
            if raw['eyebrow_raise'] > 30 or raw_left > 30 or raw_right > 30:
                raw_furrow *= 0.1
            # Suppress when mouth is open (residual crosstalk from jaw mechanics)
            if raw['mouth_open'] > 30:
                raw_furrow *= max(0, 1.0 - raw['mouth_open'] / 80.0)
            raw['brow_furrow'] = max(0, min(100, raw_furrow))
        else:
            for k in ('eyebrow_raise','eyebrow_raise_left','eyebrow_raise_right','mouth_open',
                      'smile','pucker','smirk_left','smirk_right','brow_furrow'):
                raw[k] = 0
        return raw

# ÃƒÂ¢Ã¢â‚¬Â¢Ã‚ÂÃƒÂ¢Ã¢â‚¬Â¢Ã‚ÂÃƒÂ¢Ã¢â‚¬Â¢Ã‚Â CAMERA THREAD ÃƒÂ¢Ã¢â‚¬Â¢Ã‚ÂÃƒÂ¢Ã¢â‚¬Â¢Ã‚ÂÃƒÂ¢Ã¢â‚¬Â¢Ã‚Â

def enumerate_cameras(max_test=8):
    """Probe camera indices and return list of (index, backend, name) tuples.
    Lists all cameras that can be opened, even if initial read fails (MSMF bug)."""
    results = []
    for idx in range(max_test):
        for backend, bname in [(cv2.CAP_MSMF, 'MSMF'), (cv2.CAP_DSHOW, 'DSHOW')]:
            try:
                cap = cv2.VideoCapture(idx, backend)
                if cap.isOpened():
                    cap.release()
                    label = f"Camera {idx}"
                    results.append((idx, backend, label))
                    break
            except: pass
    return results

class CameraThread(QThread):
    frame_ready = pyqtSignal(object, object, float)
    status_changed = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, cam_index=0, cam_backend=None):
        super().__init__(); self._running=False; self._mx=QMutex()
        self._cam_index = cam_index
        self._cam_backend = cam_backend

    def stop(self):
        with QMutexLocker(self._mx): self._running=False

    def run(self):
        self._running = True
        self.status_changed.emit("Opening camera...")
        if self._cam_backend is not None:
            cap = cv2.VideoCapture(self._cam_index, self._cam_backend)
        else:
            cap = cv2.VideoCapture(self._cam_index)
        if not cap.isOpened():
            self.error.emit("Could not open camera"); return
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,640); cap.set(cv2.CAP_PROP_FRAME_HEIGHT,480)
        cap.set(cv2.CAP_PROP_FPS,60)
        fm = None; mode = None
        try:
            from mediapipe.tasks import python as mpt
            from mediapipe.tasks.python import vision
            mp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),'face_landmarker.task')
            if not os.path.exists(mp_path):
                self.status_changed.emit("Downloading face model...")
                import urllib.request
                urllib.request.urlretrieve("https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task", mp_path)
            opts = vision.FaceLandmarkerOptions(
                base_options=mpt.BaseOptions(model_asset_path=mp_path),
                running_mode=vision.RunningMode.IMAGE, num_faces=1,
                min_face_detection_confidence=0.5, min_face_presence_confidence=0.5,
                min_tracking_confidence=0.5, output_face_blendshapes=False,
                output_facial_transformation_matrixes=False)
            fm = vision.FaceLandmarker.create_from_options(opts)
            mode = 'tasks'; self.status_changed.emit("Camera ready")
        except Exception as e:
            self.error.emit(f"MediaPipe init failed: {e}"); cap.release(); return

        fc=0; ft=time.time(); fps=0.0
        while True:
            with QMutexLocker(self._mx):
                if not self._running: break
            ret, frame = cap.read()
            if not ret: continue
            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            lm = None
            if mode == 'legacy':
                r = fm.process(rgb)
                if r.multi_face_landmarks: lm = r.multi_face_landmarks[0].landmark
            else:
                r = fm.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
                if r.face_landmarks and len(r.face_landmarks)>0: lm = r.face_landmarks[0]
            fc+=1; now=time.time()
            if now-ft>=0.5: fps=fc/(now-ft); fc=0; ft=now
            self.frame_ready.emit(frame, lm, fps)
        cap.release(); fm.close()

# ÃƒÂ¢Ã¢â‚¬Â¢Ã‚ÂÃƒÂ¢Ã¢â‚¬Â¢Ã‚ÂÃƒÂ¢Ã¢â‚¬Â¢Ã‚Â GESTURE DEFS ÃƒÂ¢Ã¢â‚¬Â¢Ã‚ÂÃƒÂ¢Ã¢â‚¬Â¢Ã‚ÂÃƒÂ¢Ã¢â‚¬Â¢Ã‚Â

GESTURES = [
    dict(id='eyebrow_raise', name='Eyebrow Raise', sub='Both eyebrows up', icon='\U0001F928', color='#00d4ff', ds=50, dtmin=30, dtmax=80),
    dict(id='eyebrow_raise_left', name='Left Eyebrow', sub='Left eyebrow only', icon='\U0001F914', color='#00d4ff', ds=50, dtmin=79, dtmax=100),
    dict(id='eyebrow_raise_right', name='Right Eyebrow', sub='Right eyebrow only', icon='\U0001F9D0', color='#00d4ff', ds=50, dtmin=81, dtmax=100),
    dict(id='brow_furrow', name='Brow Furrow', sub='Brows down & together', icon='\U0001F620', color='#cc44ff', ds=50, dtmin=30, dtmax=80),
    dict(id='blink', name='Blink', sub='Both eyes closed', icon='\U0001F611', color='#00ff88', ds=50, dtmin=40, dtmax=70),
    dict(id='wink_left', name='Wink Left', sub='Left eye only', icon='\U0001F609', color='#ffaa00', ds=50, dtmin=82, dtmax=100),
    dict(id='wink_right', name='Wink Right', sub='Right eye only', icon='\U0001F61C', color='#ffaa00', ds=50, dtmin=82, dtmax=100),
    dict(id='smile', name='Smile', sub='Mouth corners up', icon='\U0001F60A', color='#00ff88', ds=50, dtmin=27, dtmax=100),
    dict(id='mouth_open', name='Mouth Open', sub='Jaw drop detected', icon='\U0001F62E', color='#ff4466', ds=50, dtmin=25, dtmax=100),
    dict(id='pucker', name='Pucker', sub='Lips pursed/narrowed', icon='\U0001F48B', color='#ff66aa', ds=50, dtmin=30, dtmax=85),
    dict(id='smirk_left', name='Left Smirk', sub='Left corner raised', icon='\U0001F60F', color='#44ddaa', ds=50, dtmin=35, dtmax=90),
    dict(id='smirk_right', name='Right Smirk', sub='Right corner raised', icon='\U0001F60F', color='#44ddaa', ds=50, dtmin=35, dtmax=90),
]

ACTION_TYPES = [('none','No Action'),('key','Key Press'),('macro','Macro Sequence'),('the_rock','\U0001FAA8 The Rock'),('left_click','Left Click'),
    ('right_click','Right Click'),('double_click','Double Click'),('middle_click','Middle Click'),
    ('scroll_up','Scroll Up'),('scroll_down','Scroll Down'),('drag_toggle','Drag Toggle'),('command','Run Command')]

TRIGGER_MODES = [('single','Single Press'),('hold','Hold (Sustain)'),('toggle','Toggle On/Off')]

# Actions that support sustained hold (key down / mouse down)
_HOLDABLE_ACTIONS = {'key','left_click','right_click','middle_click'}
# Actions that repeat during hold mode (non-holdable continuous actions)
_REPEATABLE_ACTIONS = {'scroll_up','scroll_down','double_click','macro'}

# ÃƒÂ¢Ã¢â‚¬Â¢Ã‚ÂÃƒÂ¢Ã¢â‚¬Â¢Ã‚ÂÃƒÂ¢Ã¢â‚¬Â¢Ã‚Â STYLESHEET ÃƒÂ¢Ã¢â‚¬Â¢Ã‚ÂÃƒÂ¢Ã¢â‚¬Â¢Ã‚ÂÃƒÂ¢Ã¢â‚¬Â¢Ã‚Â

SS = """
QMainWindow,QWidget{background:#0a0a0f;color:#e8e8f0;font-family:"Segoe UI";font-size:12px}
QPushButton{background:#16161f;border:1px solid #2a2a3a;border-radius:6px;color:#e8e8f0;padding:6px 16px}
QPushButton:hover{border-color:#4a4a6a;background:#1a1a25}
QComboBox{background:#1e1e2a;border:1px solid #2a2a3a;border-radius:6px;color:#e8e8f0;padding:5px 10px;min-height:24px}
QComboBox::drop-down{border:none;width:20px}
QComboBox QAbstractItemView{background:#16161f;border:1px solid #2a2a3a;color:#e8e8f0;selection-background-color:#00d4ff33}
QLineEdit{background:#1e1e2a;border:1px solid #2a2a3a;border-radius:6px;color:#e8e8f0;padding:5px 10px;font-family:Consolas;font-size:11px}
QLineEdit:focus{border-color:#ffaa00;background:#ffaa0033;color:#ffaa00}
QSlider::groove:horizontal{height:4px;background:#1e1e2a;border-radius:2px}
QSlider::handle:horizontal{width:14px;height:14px;margin:-5px 0;border-radius:7px;background:#00d4ff;border:2px solid #16161f}
QCheckBox::indicator{width:18px;height:18px;border-radius:4px;border:1px solid #2a2a3a;background:#1e1e2a}
QCheckBox::indicator:checked{background:#00d4ff;border-color:#00d4ff}
QScrollArea{border:none}
QScrollBar:vertical{width:6px;background:transparent}
QScrollBar::handle:vertical{background:#2a2a3a;border-radius:3px;min-height:20px}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0}
QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{background:none}
QProgressBar{height:4px;background:#1e1e2a;border:none;border-radius:2px}
QProgressBar::chunk{border-radius:2px}
"""

# ÃƒÂ¢Ã¢â‚¬Â¢Ã‚ÂÃƒÂ¢Ã¢â‚¬Â¢Ã‚ÂÃƒÂ¢Ã¢â‚¬Â¢Ã‚Â KEY CAPTURE ÃƒÂ¢Ã¢â‚¬Â¢Ã‚ÂÃƒÂ¢Ã¢â‚¬Â¢Ã‚ÂÃƒÂ¢Ã¢â‚¬Â¢Ã‚Â

class KeyCaptureEdit(QLineEdit):
    def __init__(self, p=None):
        super().__init__(p); self.setReadOnly(True); self.setPlaceholderText("Press key...")
        self.setFixedWidth(100); self.setAlignment(Qt.AlignmentFlag.AlignCenter)
    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Control,Qt.Key.Key_Shift,Qt.Key.Key_Alt,Qt.Key.Key_Meta): return
        p = []
        if e.modifiers()&Qt.KeyboardModifier.ControlModifier: p.append('Ctrl')
        if e.modifiers()&Qt.KeyboardModifier.AltModifier: p.append('Alt')
        if e.modifiers()&Qt.KeyboardModifier.ShiftModifier: p.append('Shift')
        if e.modifiers()&Qt.KeyboardModifier.MetaModifier: p.append('Meta')
        kt = QKeySequence(e.key()).toString()
        if kt: p.append(kt)
        self.setText('+'.join(p)); self.clearFocus()

# Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â MACRO EDITOR Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â

MACRO_STEP_TYPES = [('key','Key Press'),('hold','Hold Key'),('mouse','Mouse Action'),('delay','Delay (ms)')]
MACRO_MOUSE_ACTIONS = [('left_click','Left Click'),('right_click','Right Click'),('double_click','Double Click'),
    ('middle_click','Middle Click'),('scroll_up','Scroll Up'),('scroll_down','Scroll Down')]

class MacroStepRow(QFrame):
    removed = pyqtSignal(object)
    moved_up = pyqtSignal(object)
    moved_down = pyqtSignal(object)

    def __init__(self, step_type='key', value='', parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:#1e1e2a;border:1px solid #2a2a3a;border-radius:4px;")
        self.setFixedHeight(32)
        ly = QHBoxLayout(self); ly.setContentsMargins(4,2,4,2); ly.setSpacing(4)

        self.up_btn = QPushButton("\u25B2"); self.up_btn.setFixedSize(18,18)
        self.up_btn.setStyleSheet("font-size:8px;padding:0;border:1px solid #2a2a3a;border-radius:3px;background:#16161f;color:#555570;")
        self.up_btn.clicked.connect(lambda: self.moved_up.emit(self))
        ly.addWidget(self.up_btn)
        self.dn_btn = QPushButton("\u25BC"); self.dn_btn.setFixedSize(18,18)
        self.dn_btn.setStyleSheet("font-size:8px;padding:0;border:1px solid #2a2a3a;border-radius:3px;background:#16161f;color:#555570;")
        self.dn_btn.clicked.connect(lambda: self.moved_down.emit(self))
        ly.addWidget(self.dn_btn)

        self.type_cb = QComboBox(); self.type_cb.setFixedWidth(90); self.type_cb.setFixedHeight(24)
        for v,l in MACRO_STEP_TYPES: self.type_cb.addItem(l, v)
        self.type_cb.currentIndexChanged.connect(self._on_type_changed)
        ly.addWidget(self.type_cb)

        self.key_edit = KeyCaptureEdit(); self.key_edit.setFixedWidth(80); self.key_edit.setFixedHeight(24)
        ly.addWidget(self.key_edit)

        self.mouse_cb = QComboBox(); self.mouse_cb.setFixedWidth(100); self.mouse_cb.setFixedHeight(24)
        for v,l in MACRO_MOUSE_ACTIONS: self.mouse_cb.addItem(l, v)
        self.mouse_cb.hide()
        ly.addWidget(self.mouse_cb)

        self.dur_spin = QSpinBox(); self.dur_spin.setRange(10, 5000); self.dur_spin.setValue(50)
        self.dur_spin.setSuffix(" ms"); self.dur_spin.setFixedWidth(80); self.dur_spin.setFixedHeight(24)
        self.dur_spin.setStyleSheet("background:#1e1e2a;border:1px solid #2a2a3a;border-radius:4px;color:#e8e8f0;padding:2px;")
        self.dur_spin.hide()
        ly.addWidget(self.dur_spin)

        ly.addStretch()

        rb = QPushButton("\u2715"); rb.setFixedSize(20,20)
        rb.setStyleSheet("font-size:11px;padding:0;border:none;color:#ff4466;background:transparent;")
        rb.setToolTip("Remove step"); rb.clicked.connect(lambda: self.removed.emit(self))
        ly.addWidget(rb)

        self._apply_step(step_type, value)

    def _apply_step(self, step_type, value):
        for i in range(self.type_cb.count()):
            if self.type_cb.itemData(i) == step_type: self.type_cb.setCurrentIndex(i); break
        if step_type == 'key':
            self.key_edit.setText(value)
        elif step_type == 'hold':
            parts = value.rsplit(':', 1) if ':' in value else [value, '500']
            self.key_edit.setText(parts[0])
            try: self.dur_spin.setValue(int(parts[1]))
            except: self.dur_spin.setValue(500)
        elif step_type == 'mouse':
            for i in range(self.mouse_cb.count()):
                if self.mouse_cb.itemData(i) == value: self.mouse_cb.setCurrentIndex(i); break
        elif step_type == 'delay':
            try: self.dur_spin.setValue(int(value))
            except: self.dur_spin.setValue(50)
        self._on_type_changed()

    def _on_type_changed(self):
        t = self.type_cb.currentData()
        self.key_edit.setVisible(t in ('key','hold'))
        self.mouse_cb.setVisible(t == 'mouse')
        self.dur_spin.setVisible(t in ('hold','delay'))

    def to_macro_string(self):
        t = self.type_cb.currentData()
        if t == 'key': return f"key:{self.key_edit.text()}" if self.key_edit.text() else ''
        elif t == 'hold': return f"hold:{self.key_edit.text()}:{self.dur_spin.value()}" if self.key_edit.text() else ''
        elif t == 'mouse': return f"mouse:{self.mouse_cb.currentData()}"
        elif t == 'delay': return f"delay:{self.dur_spin.value()}"
        return ''


class MacroEditor(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;border:none;")
        ly = QVBoxLayout(self); ly.setContentsMargins(0,0,0,0); ly.setSpacing(3)

        self.steps_layout = QVBoxLayout(); self.steps_layout.setContentsMargins(0,0,0,0); self.steps_layout.setSpacing(2)
        ly.addLayout(self.steps_layout)
        self.step_rows = []

        add_btn = QPushButton("+ Add Step"); add_btn.setFixedHeight(24)
        add_btn.setStyleSheet("font-size:10px;padding:2px 10px;border:1px dashed #2a2a3a;color:#00d4ff;border-radius:4px;background:transparent;")
        add_btn.clicked.connect(lambda: self.add_step())
        ly.addWidget(add_btn)

    def add_step(self, step_type='key', value=''):
        row = MacroStepRow(step_type, value)
        row.removed.connect(self._remove_step)
        row.moved_up.connect(self._move_up)
        row.moved_down.connect(self._move_down)
        self.step_rows.append(row)
        self.steps_layout.addWidget(row)

    def _remove_step(self, row):
        if row in self.step_rows:
            self.step_rows.remove(row)
            self.steps_layout.removeWidget(row)
            row.deleteLater()

    def _move_up(self, row):
        idx = self.step_rows.index(row) if row in self.step_rows else -1
        if idx > 0: self._swap(idx, idx-1)

    def _move_down(self, row):
        idx = self.step_rows.index(row) if row in self.step_rows else -1
        if idx >= 0 and idx < len(self.step_rows)-1: self._swap(idx, idx+1)

    def _swap(self, i, j):
        self.step_rows[i], self.step_rows[j] = self.step_rows[j], self.step_rows[i]
        for r in self.step_rows: self.steps_layout.removeWidget(r)
        for r in self.step_rows: self.steps_layout.addWidget(r)

    def to_macro_string(self):
        parts = [r.to_macro_string() for r in self.step_rows if r.to_macro_string()]
        return ';'.join(parts)

    def set_from_string(self, macro_str):
        for r in list(self.step_rows): self._remove_step(r)
        if not macro_str: return
        steps = parse_macro(macro_str)
        for step in steps:
            if step[0] == 'key': self.add_step('key', step[1])
            elif step[0] == 'hold': self.add_step('hold', f"{step[1]}:{step[2]}")
            elif step[0] == 'mouse': self.add_step('mouse', step[1])
            elif step[0] == 'delay': self.add_step('delay', str(step[1]))

    def clear(self):
        for r in list(self.step_rows): self._remove_step(r)

# ÃƒÂ¢Ã¢â‚¬Â¢ÃƒÂ¢Ã¢â‚¬Â¢ÃƒÂ¢Ã¢â‚¬Â¢ GESTURE CHAIN CARD ÃƒÂ¢Ã¢â‚¬Â¢ÃƒÂ¢Ã¢â‚¬Â¢ÃƒÂ¢Ã¢â‚¬Â¢

GESTURE_CHOICES = [(g['id'], f"{g['icon']} {g['name']}") for g in GESTURES]

class ChainStepRow(QFrame):
    """A single gesture step in a chain sequence."""
    removed = pyqtSignal(object)
    gesture_changed = pyqtSignal(object, str, str)  # self, old_gid, new_gid

    def __init__(self, gesture_id='', parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:#1e1e2a;border:1px solid #2a2a3a;border-radius:4px;")
        self.setFixedHeight(30)
        ly = QHBoxLayout(self); ly.setContentsMargins(6,2,4,2); ly.setSpacing(6)

        step_icon = QLabel("\u25B6"); step_icon.setFixedSize(16,16)
        step_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        step_icon.setStyleSheet("font-size:8px;color:#ffaa00;border:none;background:transparent;")
        ly.addWidget(step_icon)

        self.gcb = QComboBox(); self.gcb.setFixedHeight(24)
        self.gcb.addItem("Select gesture...", "")
        for gid, label in GESTURE_CHOICES: self.gcb.addItem(label, gid)
        if gesture_id:
            for i in range(self.gcb.count()):
                if self.gcb.itemData(i) == gesture_id: self.gcb.setCurrentIndex(i); break
        self._prev_gid = gesture_id
        self.gcb.currentIndexChanged.connect(self._on_changed)
        ly.addWidget(self.gcb, stretch=1)

        rb = QPushButton("\u2715"); rb.setFixedSize(20,20)
        rb.setStyleSheet("font-size:11px;padding:0;border:none;color:#ff4466;background:transparent;")
        rb.clicked.connect(lambda: self.removed.emit(self))
        ly.addWidget(rb)

    def _on_changed(self):
        new_gid = self.gcb.currentData() or ''
        old_gid = self._prev_gid
        self._prev_gid = new_gid
        self.gesture_changed.emit(self, old_gid, new_gid)

    def gesture_id(self):
        return self.gcb.currentData() or ''


class GestureChainCard(QFrame):
    """Card for defining a gesture chain (sequence) that triggers an action."""
    chain_deleted = pyqtSignal(object)
    gesture_claimed = pyqtSignal(str)    # gesture_id claimed by this chain
    gesture_released = pyqtSignal(str)   # gesture_id released by this chain

    def __init__(self, chain_id=0, parent=None):
        super().__init__(parent)
        self.chain_id = chain_id
        self.setStyleSheet("background:#16161f;border:1px solid #ffaa0055;border-radius:10px;")
        ly = QVBoxLayout(self); ly.setContentsMargins(12,12,12,12); ly.setSpacing(6)

        # Header
        top = QHBoxLayout()
        ic = QLabel("\u26A1"); ic.setFixedSize(30,30); ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ic.setStyleSheet("background:#ffaa0033;border-radius:6px;font-size:15px;border:none;")
        top.addWidget(ic)
        nb = QVBoxLayout(); nb.setSpacing(0)
        self.name_lbl = QLabel(f"Gesture Chain #{chain_id+1}")
        self.name_lbl.setStyleSheet("font-weight:600;font-size:13px;color:#ffaa00;border:none;")
        sub = QLabel("Sequential gesture trigger")
        sub.setStyleSheet("color:#555570;font-size:11px;border:none;")
        nb.addWidget(self.name_lbl); nb.addWidget(sub); top.addLayout(nb); top.addStretch()

        del_btn = QPushButton("\U0001F5D1 Delete"); del_btn.setFixedHeight(26)
        del_btn.setStyleSheet("font-size:10px;padding:2px 8px;border:1px solid #ff446655;color:#ff4466;border-radius:4px;background:transparent;")
        del_btn.clicked.connect(lambda: self.chain_deleted.emit(self))
        top.addWidget(del_btn)
        ly.addLayout(top)

        # Gesture sequence
        ly.addWidget(self._lbl("Gesture Sequence (in order)"))
        self.steps_layout = QVBoxLayout(); self.steps_layout.setContentsMargins(0,0,0,0); self.steps_layout.setSpacing(2)
        ly.addLayout(self.steps_layout)
        self.step_rows = []

        add_gesture_btn = QPushButton("+ Add Gesture Step"); add_gesture_btn.setFixedHeight(24)
        add_gesture_btn.setStyleSheet("font-size:10px;padding:2px 10px;border:1px dashed #ffaa0055;color:#ffaa00;border-radius:4px;background:transparent;")
        add_gesture_btn.clicked.connect(lambda: self.add_gesture_step())
        ly.addWidget(add_gesture_btn)

        # Step timeout
        h = QHBoxLayout(); h.addWidget(self._lbl("Step Timeout")); h.addStretch()
        self.timeout_val = QLabel("1500 ms")
        self.timeout_val.setStyleSheet("font-family:Consolas;font-size:11px;color:#555570;border:none;")
        h.addWidget(self.timeout_val); ly.addLayout(h)
        self.timeout_sl = QSlider(Qt.Orientation.Horizontal); self.timeout_sl.setRange(300,5000)
        self.timeout_sl.setSingleStep(100); self.timeout_sl.setValue(1500)
        self.timeout_sl.setStyleSheet("QSlider::handle:horizontal{background:#ffaa00;border:2px solid #16161f;}")
        self.timeout_sl.valueChanged.connect(lambda v: self.timeout_val.setText(f"{v} ms"))
        ly.addWidget(self.timeout_sl)

        # Action config (reuse same pattern as GestureCard)
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine); sep.setStyleSheet("color:#2a2a3a;"); ly.addWidget(sep)
        ly.addWidget(self._lbl("Chain Action"))
        ar = QHBoxLayout()
        self.ac = QComboBox()
        for v, l in ACTION_TYPES: self.ac.addItem(l, v)
        self.ac.currentIndexChanged.connect(self._oa); ar.addWidget(self.ac)
        self.ke = KeyCaptureEdit(); self.ke.hide(); ar.addWidget(self.ke)
        self.ce = QLineEdit(); self.ce.setPlaceholderText("Command..."); self.ce.hide(); ar.addWidget(self.ce)
        ly.addLayout(ar)

        self.me = MacroEditor(); self.me.hide(); ly.addWidget(self.me)

        # Progress indicator
        self.progress_lbl = QLabel("Waiting...")
        self.progress_lbl.setStyleSheet("font-family:Consolas;font-size:10px;color:#555570;border:none;padding-top:4px;")
        ly.addWidget(self.progress_lbl)

    def _lbl(self, t):
        l = QLabel(t); l.setStyleSheet("font-size:11px;border:none;"); return l

    def _oa(self):
        a = self.ac.currentData()
        self.ke.setVisible(a == 'key'); self.ce.setVisible(a == 'command'); self.me.setVisible(a == 'macro')

    def add_gesture_step(self, gesture_id=''):
        row = ChainStepRow(gesture_id)
        row.removed.connect(self._remove_gesture_step)
        row.gesture_changed.connect(self._on_gesture_changed)
        self.step_rows.append(row)
        self.steps_layout.addWidget(row)
        if gesture_id: self.gesture_claimed.emit(gesture_id)

    def _remove_gesture_step(self, row):
        if row in self.step_rows:
            gid = row.gesture_id()
            self.step_rows.remove(row)
            self.steps_layout.removeWidget(row)
            row.deleteLater()
            if gid: self.gesture_released.emit(gid)

    def _on_gesture_changed(self, row, old_gid, new_gid):
        if old_gid: self.gesture_released.emit(old_gid)
        if new_gid: self.gesture_claimed.emit(new_gid)

    def get_gesture_sequence(self):
        return [r.gesture_id() for r in self.step_rows if r.gesture_id()]

    def get_all_gesture_ids(self):
        """Return set of all gesture IDs used by this chain."""
        return {r.gesture_id() for r in self.step_rows if r.gesture_id()}

    def get_action_state(self):
        return dict(action=self.ac.currentData(), keyBind=self.ke.text(),
                    command=self.ce.text(), macro=self.me.to_macro_string())

    def get_state(self):
        return dict(gestures=self.get_gesture_sequence(),
                    timeout=self.timeout_sl.value(),
                    action=self.ac.currentData(), keyBind=self.ke.text(),
                    command=self.ce.text(), macro=self.me.to_macro_string())

    def set_state(self, s):
        # Clear existing steps
        for r in list(self.step_rows): self._remove_gesture_step(r)
        for gid in s.get('gestures', []): self.add_gesture_step(gid)
        self.timeout_sl.setValue(s.get('timeout', 1500))
        a = s.get('action', 'none')
        for i in range(self.ac.count()):
            if self.ac.itemData(i) == a: self.ac.setCurrentIndex(i); break
        self.ke.setText(s.get('keyBind', '')); self.ce.setText(s.get('command', ''))
        self.me.set_from_string(s.get('macro', ''))

    def set_progress(self, step_idx, total):
        if step_idx == 0:
            self.progress_lbl.setText("Waiting...")
            self.progress_lbl.setStyleSheet("font-family:Consolas;font-size:10px;color:#555570;border:none;padding-top:4px;")
        else:
            dots = "\u2B24 " * step_idx + "\u25CB " * (total - step_idx)
            self.progress_lbl.setText(f"Progress: {dots.strip()} ({step_idx}/{total})")
            self.progress_lbl.setStyleSheet("font-family:Consolas;font-size:10px;color:#ffaa00;border:none;padding-top:4px;")


# ••• MORSE CHAIN CARD •••

from PyQt6.QtGui import QPainter, QColor, QPen, QBrush
from PyQt6.QtCore import QRect, QRectF


class MorseProgressWidget(QWidget):
    """Custom widget that draws morse-code hold progress as split-pill cells."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(24)
        self.setMinimumWidth(100)
        self.completed = []       # list of 'S' or 'L'
        self.in_progress = 0.0   # 0.0-0.5 = short zone, 0.5-1.0 = long zone
        self.active = False
        self.matched = False
        self._flash = 0

    def set_state(self, completed, in_progress_frac, active):
        self.completed = completed
        self.in_progress = in_progress_frac
        self.active = active
        self.update()

    def flash_match(self):
        self.matched = True; self._flash = 6; self.update()

    def reset(self):
        self.completed = []; self.in_progress = 0.0; self.active = False
        self.matched = False; self._flash = 0; self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width(); h = self.height()
        cell_gap = 4
        n_cells = len(self.completed) + (1 if self.active else 0)
        if n_cells == 0:
            p.setPen(QColor('#555570'))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, '  Waiting for gesture...')
            p.end(); return
        cir_d = h - 6; pill_w = int(cir_d * 2.5)
        cell_widths = []
        for t in self.completed:
            cell_widths.append(cir_d if t == 'S' else pill_w)
        if self.active: cell_widths.append(pill_w)
        x = 4; cy = h // 2
        for i, t in enumerate(self.completed):
            cw = cell_widths[i]
            if self._flash > 0: clr = QColor('#00ff88')
            elif t == 'S': clr = QColor('#00d4ff')
            else: clr = QColor('#ffaa00')
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(clr))
            if t == 'S': p.drawEllipse(x, cy - cir_d//2, cir_d, cir_d)
            else:
                r = cir_d // 2; p.drawRoundedRect(x, cy - r, cw, cir_d, r, r)
            x += cw + cell_gap
        if self.active:
            cw = cell_widths[-1]; r = cir_d // 2; frac = self.in_progress
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(QColor('#1e1e2a')))
            p.drawRoundedRect(x, cy - r, cw, cir_d, r, r)
            p.setPen(QPen(QColor('#2a2a3a'), 1)); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(x, cy - r, cw, cir_d, r, r); p.setPen(Qt.PenStyle.NoPen)
            half = cw // 2
            if frac <= 0.5:
                fill_w = int(frac * 2 * half)
                if fill_w > 0:
                    p.save(); p.setClipRect(QRectF(x, cy - r, fill_w, cir_d))
                    p.setBrush(QBrush(QColor('#00d4ff88')))
                    p.drawRoundedRect(x, cy - r, cw, cir_d, r, r); p.restore()
                p.setPen(QPen(QColor('#2a2a3a'), 1))
                p.drawLine(x + half, cy - r + 2, x + half, cy + r - 2); p.setPen(Qt.PenStyle.NoPen)
            else:
                p.save(); p.setClipRect(QRectF(x, cy - r, half, cir_d))
                p.setBrush(QBrush(QColor('#00d4ffcc')))
                p.drawRoundedRect(x, cy - r, cw, cir_d, r, r); p.restore()
                right_frac = (frac - 0.5) * 2; right_fill = int(right_frac * half)
                if right_fill > 0:
                    p.save(); p.setClipRect(QRectF(x + half, cy - r, right_fill, cir_d))
                    p.setBrush(QBrush(QColor('#ffaa00aa')))
                    p.drawRoundedRect(x, cy - r, cw, cir_d, r, r); p.restore()
                p.setPen(QPen(QColor('#ffaa00'), 1))
                p.drawLine(x + half, cy - r + 2, x + half, cy + r - 2); p.setPen(Qt.PenStyle.NoPen)
        if self._flash > 0:
            self._flash -= 1
            if self._flash == 0: self.matched = False
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(80, self.update)
        p.end()


class MorsePatternRow(QFrame):
    """One row: a morse pattern (S/L buttons) + action assignment."""
    removed = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:#1a1a26;border:1px solid #2a2a3a;border-radius:6px;")
        self._symbols = []
        outer = QVBoxLayout(self); outer.setContentsMargins(8,6,8,6); outer.setSpacing(4)
        top = QHBoxLayout(); top.setSpacing(4)
        self.sym_frame = QFrame()
        self.sym_frame.setStyleSheet("background:transparent;border:none;")
        self.sym_layout = QHBoxLayout(self.sym_frame)
        self.sym_layout.setContentsMargins(0,0,0,0); self.sym_layout.setSpacing(3)
        top.addWidget(self.sym_frame, stretch=1)
        add_s = QPushButton("\u00b7S"); add_s.setFixedSize(28,22)
        add_s.setStyleSheet("font-size:10px;font-weight:700;padding:0;border:1px solid #00d4ff55;color:#00d4ff;border-radius:4px;background:#00d4ff15;")
        add_s.setToolTip("Add Short hold"); add_s.clicked.connect(lambda: self._add_symbol('S')); top.addWidget(add_s)
        add_l = QPushButton("\u2501L"); add_l.setFixedSize(28,22)
        add_l.setStyleSheet("font-size:10px;font-weight:700;padding:0;border:1px solid #ffaa0055;color:#ffaa00;border-radius:4px;background:#ffaa0015;")
        add_l.setToolTip("Add Long hold"); add_l.clicked.connect(lambda: self._add_symbol('L')); top.addWidget(add_l)
        clr = QPushButton("\u2715"); clr.setFixedSize(22,22)
        clr.setStyleSheet("font-size:10px;padding:0;border:none;color:#ff4466;background:transparent;")
        clr.setToolTip("Clear pattern"); clr.clicked.connect(self._clear_symbols); top.addWidget(clr)
        rb = QPushButton("\U0001F5D1"); rb.setFixedSize(22,22)
        rb.setStyleSheet("font-size:11px;padding:0;border:none;color:#555570;background:transparent;")
        rb.setToolTip("Remove this pattern row"); rb.clicked.connect(lambda: self.removed.emit(self)); top.addWidget(rb)
        outer.addLayout(top)
        bot = QHBoxLayout(); bot.setSpacing(4)
        arr = QLabel("\u2192"); arr.setStyleSheet("color:#555570;font-size:12px;border:none;"); bot.addWidget(arr)
        self.ac = QComboBox(); self.ac.setFixedHeight(22); self.ac.setStyleSheet("font-size:10px;")
        for v, l in ACTION_TYPES: self.ac.addItem(l, v)
        self.ac.currentIndexChanged.connect(self._oa); bot.addWidget(self.ac, stretch=1)
        self.ke = KeyCaptureEdit(); self.ke.setFixedWidth(80); self.ke.setFixedHeight(22); self.ke.hide(); bot.addWidget(self.ke)
        self.ce = QLineEdit(); self.ce.setPlaceholderText("Command..."); self.ce.setFixedHeight(22); self.ce.hide(); bot.addWidget(self.ce)
        outer.addLayout(bot)
        self.me = MacroEditor(); self.me.hide(); outer.addWidget(self.me)
        self._rebuild_symbols()

    def _oa(self):
        a = self.ac.currentData()
        self.ke.setVisible(a == 'key'); self.ce.setVisible(a == 'command'); self.me.setVisible(a == 'macro')

    def _add_symbol(self, sym):
        self._symbols.append(sym); self._rebuild_symbols()

    def _clear_symbols(self):
        self._symbols = []; self._rebuild_symbols()

    def _rebuild_symbols(self):
        while self.sym_layout.count():
            item = self.sym_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        for i, sym in enumerate(self._symbols):
            if sym == 'S':
                lbl = QLabel("\u00b7"); lbl.setFixedSize(14, 20); lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl.setStyleSheet("background:#00d4ff33;border:1px solid #00d4ff66;border-radius:7px;color:#00d4ff;font-size:14px;font-weight:700;")
            else:
                lbl = QLabel("\u2501"); lbl.setFixedSize(26, 20); lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl.setStyleSheet("background:#ffaa0033;border:1px solid #ffaa0066;border-radius:4px;color:#ffaa00;font-size:11px;font-weight:700;")
            idx = i; lbl.mousePressEvent = lambda e, ix=idx: self._remove_symbol(ix)
            lbl.setToolTip("Click to remove"); self.sym_layout.addWidget(lbl)
        if not self._symbols:
            hint = QLabel("click \u00b7S or \u2501L to build pattern")
            hint.setStyleSheet("color:#555570;font-size:10px;border:none;"); self.sym_layout.addWidget(hint)
        self.sym_layout.addStretch()

    def _remove_symbol(self, idx):
        if 0 <= idx < len(self._symbols): self._symbols.pop(idx); self._rebuild_symbols()

    def get_pattern(self): return list(self._symbols)
    def set_pattern(self, syms): self._symbols = list(syms); self._rebuild_symbols()
    def get_action_state(self):
        return dict(action=self.ac.currentData(), keyBind=self.ke.text(), command=self.ce.text(), macro=self.me.to_macro_string())
    def set_action_state(self, s):
        a = s.get('action', 'none')
        for i in range(self.ac.count()):
            if self.ac.itemData(i) == a: self.ac.setCurrentIndex(i); break
        self.ke.setText(s.get('keyBind', '')); self.ce.setText(s.get('command', '')); self.me.set_from_string(s.get('macro', ''))
    def get_state(self): return dict(pattern=self._symbols, **self.get_action_state())
    def set_state(self, s): self.set_pattern(s.get('pattern', [])); self.set_action_state(s)


class MorseChainCard(QFrame):
    """Morse-code gesture chain: one gesture + short/long thresholds + pattern->action rows."""
    chain_deleted = pyqtSignal(object)
    gesture_claimed = pyqtSignal(str)
    gesture_released = pyqtSignal(str)

    def __init__(self, chain_id=0, parent=None):
        super().__init__(parent)
        self.chain_id = chain_id
        self._cur_gesture = ''
        self.setStyleSheet("background:#16161f;border:1px solid #ff884455;border-radius:10px;")
        ly = QVBoxLayout(self); ly.setContentsMargins(12,12,12,12); ly.setSpacing(6)
        top = QHBoxLayout()
        ic = QLabel("\u2505"); ic.setFixedSize(30,30); ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ic.setStyleSheet("background:#ff884433;border-radius:6px;font-size:15px;border:none;"); top.addWidget(ic)
        nb = QVBoxLayout(); nb.setSpacing(0)
        self.name_lbl = QLabel(f"Morse Chain #{chain_id+1}")
        self.name_lbl.setStyleSheet("font-weight:600;font-size:13px;color:#ff8844;border:none;")
        sub = QLabel("Short \u00b7 Long \u2501 hold sequences \u2192 actions")
        sub.setStyleSheet("color:#555570;font-size:11px;border:none;")
        nb.addWidget(self.name_lbl); nb.addWidget(sub); top.addLayout(nb); top.addStretch()
        del_btn = QPushButton("\U0001F5D1 Delete"); del_btn.setFixedHeight(26)
        del_btn.setStyleSheet("font-size:10px;padding:2px 8px;border:1px solid #ff446655;color:#ff4466;border-radius:4px;background:transparent;")
        del_btn.clicked.connect(lambda: self.chain_deleted.emit(self)); top.addWidget(del_btn)
        ly.addLayout(top)
        ly.addWidget(self._lbl("Trigger Gesture"))
        self.gcb = QComboBox(); self.gcb.setFixedHeight(26)
        self.gcb.addItem("Select gesture...", "")
        for gid, label in GESTURE_CHOICES: self.gcb.addItem(label, gid)
        self.gcb.currentIndexChanged.connect(self._on_gesture_changed); ly.addWidget(self.gcb)
        sep0 = QFrame(); sep0.setFrameShape(QFrame.Shape.HLine); sep0.setStyleSheet("color:#2a2a3a;"); ly.addWidget(sep0)
        th_row = QHBoxLayout(); th_row.setSpacing(16)
        sh_col = QVBoxLayout(); sh_col.setSpacing(2)
        sh_hdr = QHBoxLayout()
        sh_lbl = QLabel("Short Hold"); sh_lbl.setStyleSheet("font-size:11px;color:#00d4ff;border:none;font-weight:600;")
        sh_hdr.addWidget(sh_lbl); sh_hdr.addStretch()
        self.sh_val = QLabel("200 ms"); self.sh_val.setStyleSheet("font-family:Consolas;font-size:11px;color:#00d4ff;border:none;")
        sh_hdr.addWidget(self.sh_val); sh_col.addLayout(sh_hdr)
        self.sh_sl = QSlider(Qt.Orientation.Horizontal); self.sh_sl.setRange(50,1000); self.sh_sl.setSingleStep(25); self.sh_sl.setValue(200)
        self.sh_sl.setStyleSheet("QSlider::handle:horizontal{background:#00d4ff;border:2px solid #16161f;}")
        self.sh_sl.valueChanged.connect(lambda v: self.sh_val.setText(f"{v} ms")); sh_col.addWidget(self.sh_sl)
        th_row.addLayout(sh_col, stretch=1)
        lh_col = QVBoxLayout(); lh_col.setSpacing(2)
        lh_hdr = QHBoxLayout()
        lh_lbl = QLabel("Long Hold"); lh_lbl.setStyleSheet("font-size:11px;color:#ffaa00;border:none;font-weight:600;")
        lh_hdr.addWidget(lh_lbl); lh_hdr.addStretch()
        self.lh_val = QLabel("600 ms"); self.lh_val.setStyleSheet("font-family:Consolas;font-size:11px;color:#ffaa00;border:none;")
        lh_hdr.addWidget(self.lh_val); lh_col.addLayout(lh_hdr)
        self.lh_sl = QSlider(Qt.Orientation.Horizontal); self.lh_sl.setRange(200,3000); self.lh_sl.setSingleStep(50); self.lh_sl.setValue(600)
        self.lh_sl.setStyleSheet("QSlider::handle:horizontal{background:#ffaa00;border:2px solid #16161f;}")
        self.lh_sl.valueChanged.connect(lambda v: self.lh_val.setText(f"{v} ms")); lh_col.addWidget(self.lh_sl)
        th_row.addLayout(lh_col, stretch=1); ly.addLayout(th_row)
        ito_row = QHBoxLayout(); ito_row.addWidget(self._lbl("Symbol Timeout")); ito_row.addStretch()
        self.timeout_val = QLabel("1500 ms"); self.timeout_val.setStyleSheet("font-family:Consolas;font-size:11px;color:#555570;border:none;")
        ito_row.addWidget(self.timeout_val); ly.addLayout(ito_row)
        self.timeout_sl = QSlider(Qt.Orientation.Horizontal); self.timeout_sl.setRange(300,5000); self.timeout_sl.setSingleStep(100); self.timeout_sl.setValue(1500)
        self.timeout_sl.setStyleSheet("QSlider::handle:horizontal{background:#ffaa00;border:2px solid #16161f;}")
        self.timeout_sl.valueChanged.connect(lambda v: self.timeout_val.setText(f"{v} ms")); ly.addWidget(self.timeout_sl)
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine); sep.setStyleSheet("color:#2a2a3a;"); ly.addWidget(sep)
        patr_hdr = QHBoxLayout(); patr_hdr.addWidget(self._lbl("Morse Patterns \u2192 Actions")); patr_hdr.addStretch()
        add_pat_btn = QPushButton("+ Pattern"); add_pat_btn.setFixedHeight(22)
        add_pat_btn.setStyleSheet("font-size:10px;padding:2px 8px;border:1px dashed #ff884455;color:#ff8844;border-radius:4px;background:transparent;")
        add_pat_btn.clicked.connect(self.add_pattern_row); patr_hdr.addWidget(add_pat_btn); ly.addLayout(patr_hdr)
        self.patterns_layout = QVBoxLayout(); self.patterns_layout.setContentsMargins(0,0,0,0); self.patterns_layout.setSpacing(3)
        ly.addLayout(self.patterns_layout); self.pattern_rows = []
        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine); sep2.setStyleSheet("color:#2a2a3a;"); ly.addWidget(sep2)
        prog_hdr = QHBoxLayout(); prog_hdr.addWidget(self._lbl("Live Morse Input")); prog_hdr.addStretch()
        self.reset_btn = QPushButton("\u2715 Reset"); self.reset_btn.setFixedHeight(20)
        self.reset_btn.setStyleSheet("font-size:10px;padding:1px 6px;border:1px solid #2a2a3a;color:#555570;border-radius:3px;background:transparent;")
        prog_hdr.addWidget(self.reset_btn); ly.addLayout(prog_hdr)
        self.progress_widget = MorseProgressWidget(); ly.addWidget(self.progress_widget)

    def _lbl(self, t):
        l = QLabel(t); l.setStyleSheet("font-size:11px;border:none;"); return l
    def _on_gesture_changed(self):
        new_gid = self.gcb.currentData() or ''
        old_gid = self._cur_gesture
        if old_gid == new_gid: return
        if old_gid: self.gesture_released.emit(old_gid)
        self._cur_gesture = new_gid
        if new_gid: self.gesture_claimed.emit(new_gid)
    def gesture_id(self): return self.gcb.currentData() or ''
    def get_all_gesture_ids(self):
        gid = self.gesture_id(); return {gid} if gid else set()
    def add_pattern_row(self):
        row = MorsePatternRow(); row.removed.connect(self._remove_pattern_row)
        self.pattern_rows.append(row); self.patterns_layout.addWidget(row)
    def _remove_pattern_row(self, row):
        if row in self.pattern_rows:
            self.pattern_rows.remove(row); self.patterns_layout.removeWidget(row); row.deleteLater()
    def get_patterns(self):
        return [(row.get_pattern(), row.get_action_state()) for row in self.pattern_rows if row.get_pattern()]
    def get_state(self):
        return dict(type='morse', gesture=self.gesture_id(), short_ms=self.sh_sl.value(),
            long_ms=self.lh_sl.value(), timeout=self.timeout_sl.value(),
            patterns=[row.get_state() for row in self.pattern_rows])
    def set_state(self, s):
        gid = s.get('gesture', '')
        for i in range(self.gcb.count()):
            if self.gcb.itemData(i) == gid: self.gcb.setCurrentIndex(i); break
        self.sh_sl.setValue(s.get('short_ms', 200)); self.lh_sl.setValue(s.get('long_ms', 600))
        self.timeout_sl.setValue(s.get('timeout', 1500))
        for r in list(self.pattern_rows): self._remove_pattern_row(r)
        for ps in s.get('patterns', []): self.add_pattern_row(); self.pattern_rows[-1].set_state(ps)
    def set_progress(self, completed, in_progress_frac, active):
        self.progress_widget.set_state(completed, in_progress_frac, active)
    def flash_match(self): self.progress_widget.flash_match()
    def connect_reset(self, slot): self.reset_btn.clicked.connect(slot)


# ÃƒÂ¢Ã¢â‚¬Â¢Ã‚ÂÃƒÂ¢Ã¢â‚¬Â¢Ã‚ÂÃƒÂ¢Ã¢â‚¬Â¢Ã‚Â GESTURE CARD ÃƒÂ¢Ã¢â‚¬Â¢Ã‚ÂÃƒÂ¢Ã¢â‚¬Â¢Ã‚ÂÃƒÂ¢Ã¢â‚¬Â¢Ã‚Â

def _sens_mult(v):
    """Slider 1-100 -> multiplier. 1=0.2x, 50=1.0x, 100=3.0x."""
    if v <= 50:
        return 0.2 + 0.8 * ((v - 1) / 49.0)   # linear 0.2 to 1.0
    else:
        return 1.0 + 2.0 * ((v - 50) / 50.0)   # linear 1.0 to 3.0

class GestureCard(QFrame):
    def __init__(self, g):
        super().__init__(); self.g=g; self.gid=g['id']; self.color=g['color']
        self.setStyleSheet(f"background:#16161f;border:1px solid #2a2a3a;border-radius:10px;")
        ly = QVBoxLayout(self); ly.setContentsMargins(12,12,12,12); ly.setSpacing(6)

        top = QHBoxLayout()
        ic = QLabel(g['icon']); ic.setFixedSize(30,30); ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ic.setStyleSheet(f"background:{self.color}33;border-radius:6px;font-size:15px;border:none;")
        top.addWidget(ic)
        nb = QVBoxLayout(); nb.setSpacing(0)
        n=QLabel(g['name']); n.setStyleSheet("font-weight:600;font-size:13px;border:none;")
        s=QLabel(g['sub']); s.setStyleSheet("color:#555570;font-size:11px;border:none;")
        nb.addWidget(n); nb.addWidget(s); top.addLayout(nb); top.addStretch()
        self.en = QCheckBox(); self.en.setChecked(True); top.addWidget(self.en)
        ly.addLayout(top)

        # Sensitivity (now a multiplier)
        h=QHBoxLayout(); h.addWidget(self._lbl("Sensitivity")); h.addStretch()
        self.sv=self._mono(f"{_sens_mult(g['ds']):.1f}x"); h.addWidget(self.sv); ly.addLayout(h)
        self.ss=QSlider(Qt.Orientation.Horizontal); self.ss.setRange(1,100); self.ss.setValue(g['ds'])
        self.ss.valueChanged.connect(lambda v: self.sv.setText(f"{_sens_mult(v):.1f}x")); ly.addWidget(self.ss)

        # Threshold
        h2=QHBoxLayout(); h2.addWidget(self._lbl("Threshold")); h2.addStretch()
        self.tv=self._mono(f"{g['dtmin']}\u2013{g['dtmax']}"); h2.addWidget(self.tv); ly.addLayout(h2)
        tr=QHBoxLayout()
        self.tmin=QSlider(Qt.Orientation.Horizontal); self.tmin.setRange(0,100); self.tmin.setValue(g['dtmin'])
        self.tmax=QSlider(Qt.Orientation.Horizontal); self.tmax.setRange(0,100); self.tmax.setValue(g['dtmax'])
        tol=QLabel("to"); tol.setStyleSheet("font-size:11px;color:#555570;border:none;")
        tr.addWidget(self.tmin); tr.addWidget(tol); tr.addWidget(self.tmax); ly.addLayout(tr)
        self.tmin.valueChanged.connect(self._ut); self.tmax.valueChanged.connect(self._ut)

        # Live bar
        self.lb=QProgressBar(); self.lb.setRange(0,100); self.lb.setTextVisible(False); self.lb.setFixedHeight(4)
        self.lb.setStyleSheet(f"QProgressBar::chunk{{background:{self.color};border-radius:2px;}}"); ly.addWidget(self.lb)

        # Action
        sep=QFrame(); sep.setFrameShape(QFrame.Shape.HLine); sep.setStyleSheet("color:#2a2a3a;"); ly.addWidget(sep)
        ly.addWidget(self._lbl("Trigger Action"))
        ar=QHBoxLayout()
        self.ac=QComboBox()
        for v,l in ACTION_TYPES: self.ac.addItem(l,v)
        self.ac.currentIndexChanged.connect(self._oa); ar.addWidget(self.ac)
        self.ke=KeyCaptureEdit(); self.ke.hide(); ar.addWidget(self.ke)
        self.ce=QLineEdit(); self.ce.setPlaceholderText("Command..."); self.ce.hide(); ar.addWidget(self.ce)
        ly.addLayout(ar)

        # Macro editor (visible when action type is 'macro')
        self.me=MacroEditor(); self.me.hide(); ly.addWidget(self.me)

        # Trigger mode
        ly.addWidget(self._lbl("Trigger Mode"))
        mr=QHBoxLayout()
        self.tm=QComboBox()
        for v,l in TRIGGER_MODES: self.tm.addItem(l,v)
        self.tm.setToolTip("Single Press: fire once per activation\nHold (Sustain): held while gesture active\nToggle: first activation starts, second stops")
        mr.addWidget(self.tm)
        self.tml=QLabel(""); self.tml.setStyleSheet("font-size:10px;color:#555570;border:none;"); mr.addWidget(self.tml)
        self.tm.currentIndexChanged.connect(self._otm); ly.addLayout(mr)

    def _lbl(self,t): l=QLabel(t); l.setStyleSheet("font-size:11px;border:none;"); return l
    def _mono(self,t): l=QLabel(t); l.setStyleSheet("font-family:Consolas;font-size:11px;color:#555570;border:none;"); return l
    def _ut(self): self.tv.setText(f"{self.tmin.value()}\u2013{self.tmax.value()}")
    def _oa(self):
        a=self.ac.currentData()
        self.ke.setVisible(a=='key')
        self.ce.setVisible(a=='command')
        self.me.setVisible(a=='macro')
    def _otm(self):
        m=self.tm.currentData()
        hints = {'single':'','hold':'Action sustained while gesture held','toggle':'Tap gesture to start/stop'}
        self.tml.setText(hints.get(m,''))
    def set_live(self,v): self.lb.setValue(int(v))
    def get_state(self):
        return dict(enabled=self.en.isChecked(), sensitivity=self.ss.value(),
            thresholdMin=self.tmin.value(), thresholdMax=self.tmax.value(),
            action=self.ac.currentData(), keyBind=self.ke.text(), command=self.ce.text(),
            macro=self.me.to_macro_string(), triggerMode=self.tm.currentData())
    def set_state(self,s):
        self.en.setChecked(s.get('enabled',True)); self.ss.setValue(s.get('sensitivity',50))
        self.tmin.setValue(s.get('thresholdMin',20)); self.tmax.setValue(s.get('thresholdMax',80))
        a=s.get('action','none')
        for i in range(self.ac.count()):
            if self.ac.itemData(i)==a: self.ac.setCurrentIndex(i); break
        self.ke.setText(s.get('keyBind','')); self.ce.setText(s.get('command',''))
        self.me.set_from_string(s.get('macro',''))
        tm=s.get('triggerMode','single')
        for i in range(self.tm.count()):
            if self.tm.itemData(i)==tm: self.tm.setCurrentIndex(i); break
    def reset_def(self):
        g=self.g; self.en.setChecked(True); self.ss.setValue(g['ds'])
        self.tmin.setValue(g['dtmin']); self.tmax.setValue(g['dtmax'])
        self.ac.setCurrentIndex(0); self.ke.clear(); self.ce.clear(); self.me.clear()
        self.tm.setCurrentIndex(0)

# ÃƒÂ¢Ã¢â‚¬Â¢Ã‚ÂÃƒÂ¢Ã¢â‚¬Â¢Ã‚ÂÃƒÂ¢Ã¢â‚¬Â¢Ã‚Â MAIN WINDOW ÃƒÂ¢Ã¢â‚¬Â¢Ã‚ÂÃƒÂ¢Ã¢â‚¬Â¢Ã‚ÂÃƒÂ¢Ã¢â‚¬Â¢Ã‚Â

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FaceCommand"); self.setMinimumSize(1000,650); self.resize(1200,750)
        self.det = GestureDetector(); self.cam = None
        self.sm = {g['id']:0.0 for g in GESTURES}; self.lv = dict(self.sm)
        self.ta = {g['id']:False for g in GESTURES}; self.lt = {g['id']:0.0 for g in GESTURES}
        self.hs = {g['id']:0.0 for g in GESTURES}
        # Phase 1: hold/toggle state tracking
        self.hold_active = {g['id']:False for g in GESTURES}   # currently holding key/mouse down
        self.toggle_state = {g['id']:False for g in GESTURES}  # toggle is currently on
        self.repeat_lt = {g['id']:0.0 for g in GESTURES}       # last repeat fire time
        self.dc = 0; self.alog = deque(maxlen=50)
        self.cards={}; self.rbars={}; self.rvals={}
        # Gesture chains
        self.chains = []          # list of GestureChainCard widgets
        self.morse_chains = []    # list of MorseChainCard widgets
        self.chain_counter = 0    # for unique chain IDs
        self.chain_state = {}     # chain_id -> {step:int, last_time:float, prev_active:set}
        self._build()

    def _build(self):
        c=QWidget(); self.setCentralWidget(c); root=QVBoxLayout(c); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        # Header
        hdr=QFrame(); hdr.setStyleSheet("background:#12121a;border-bottom:1px solid #2a2a3a;"); hdr.setFixedHeight(50)
        hl=QHBoxLayout(hdr); hl.setContentsMargins(16,0,16,0)
        logo=QLabel("\U0001F441"); logo.setFixedSize(28,28); logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setStyleSheet("background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #00d4ff,stop:1 #aa66ff);border-radius:6px;font-size:14px;")
        hl.addWidget(logo)
        t=QLabel("FaceCommand"); t.setStyleSheet("font-family:Consolas;font-weight:600;font-size:14px;")
        hl.addWidget(t)
        v=QLabel("v1.4 native"); v.setStyleSheet("color:#555570;font-size:11px;"); hl.addWidget(v); hl.addStretch()
        self.stl=QLabel(); self._ss("Camera Off","#ff4466"); hl.addWidget(self.stl)
        # Camera selector
        self.cam_cb=QComboBox(); self.cam_cb.setMinimumWidth(200); self.cam_cb.setFixedHeight(28)
        self.cam_cb.setStyleSheet("QComboBox{background:#1e1e2a;border:1px solid #2a2a3a;border-radius:6px;color:#e8e8f0;padding:3px 8px;font-size:11px;}")
        self.cam_cb.addItem("Scanning cameras...", None)
        hl.addWidget(self.cam_cb)
        self.rescan_btn=QPushButton("\u27F3"); self.rescan_btn.setFixedSize(28,28)
        self.rescan_btn.setStyleSheet("font-size:13px;padding:0;border:1px solid #2a2a3a;border-radius:6px;background:#1e1e2a;color:#00d4ff;")
        self.rescan_btn.setToolTip("Rescan cameras")
        self.rescan_btn.clicked.connect(self._rescan_cameras)
        hl.addWidget(self.rescan_btn)
        self._available_cams = []
        threading.Thread(target=self._scan_cameras, daemon=True).start()
        self.rcb=QPushButton("\u27F3 Recalibrate"); self.rcb.setMinimumWidth(100); self.rcb.clicked.connect(self._recal); self.rcb.hide(); hl.addWidget(self.rcb)
        self.cb=QPushButton("\u25B6 Start Camera"); self.cb.setMinimumWidth(140); self.cb.clicked.connect(self._tc); hl.addWidget(self.cb)
        self._set_btn_primary()
        root.addWidget(hdr)

        # Body
        sp=QSplitter(Qt.Orientation.Horizontal); sp.setHandleWidth(1); sp.setStyleSheet("QSplitter::handle{background:#2a2a3a;}")
        left=QWidget(); left.setStyleSheet("background:#12121a;"); ll=QVBoxLayout(left); ll.setContentsMargins(0,0,0,0); ll.setSpacing(0)
        self.vl=QLabel("\U0001F4F7  Start Camera"); self.vl.setFixedSize(320,240); self.vl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.vl.setStyleSheet("background:#000;border-bottom:1px solid #2a2a3a;font-size:12px;color:#555570;"); ll.addWidget(self.vl)

        # Zoom & Pan controls
        zpf=QFrame(); zpf.setStyleSheet("background:#12121a;border-bottom:1px solid #2a2a3a;")
        zpl=QVBoxLayout(zpf); zpl.setContentsMargins(12,4,12,4); zpl.setSpacing(3)
        zr=QHBoxLayout(); zr.setSpacing(8)
        zi=QLabel("\U0001F50D"); zi.setFixedSize(20,20); zi.setAlignment(Qt.AlignmentFlag.AlignCenter)
        zi.setStyleSheet("background:#aa66ff22;border-radius:4px;font-size:11px;border:none;"); zr.addWidget(zi)
        zlbl=QLabel("Zoom"); zlbl.setStyleSheet("font-size:11px;color:#8888a0;border:none;"); zr.addWidget(zlbl)
        self.zs=QSlider(Qt.Orientation.Horizontal); self.zs.setRange(100,300); self.zs.setValue(100)
        self.zs.setStyleSheet("QSlider::handle:horizontal{background:#aa66ff;border:2px solid #16161f;}"); zr.addWidget(self.zs, stretch=1)
        self.zvl=QLabel("1.0x"); self.zvl.setStyleSheet("font-family:Consolas;font-size:11px;color:#aa66ff;min-width:32px;border:none;")
        self.zvl.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter); zr.addWidget(self.zvl)
        self.zs.valueChanged.connect(lambda v: self.zvl.setText(f"{v/100:.1f}x")); zpl.addLayout(zr)
        pxr=QHBoxLayout(); pxr.setSpacing(8)
        pxi=QLabel("\u2194"); pxi.setFixedSize(20,20); pxi.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pxi.setStyleSheet("background:#ff884422;border-radius:4px;font-size:13px;border:none;color:#ff8844;"); pxr.addWidget(pxi)
        pxlbl=QLabel("Pan X"); pxlbl.setStyleSheet("font-size:11px;color:#8888a0;border:none;"); pxr.addWidget(pxlbl)
        self.pxs=QSlider(Qt.Orientation.Horizontal); self.pxs.setRange(-100,100); self.pxs.setValue(0)
        self.pxs.setStyleSheet("QSlider::handle:horizontal{background:#ff8844;border:2px solid #16161f;}"); pxr.addWidget(self.pxs, stretch=1)
        self.pxvl=QLabel("0"); self.pxvl.setStyleSheet("font-family:Consolas;font-size:11px;color:#ff8844;min-width:32px;border:none;")
        self.pxvl.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter); pxr.addWidget(self.pxvl)
        self.pxs.valueChanged.connect(lambda v: self.pxvl.setText(str(v))); zpl.addLayout(pxr)
        pyr=QHBoxLayout(); pyr.setSpacing(8)
        pyi=QLabel("\u2195"); pyi.setFixedSize(20,20); pyi.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pyi.setStyleSheet("background:#ff884422;border-radius:4px;font-size:13px;border:none;color:#ff8844;"); pyr.addWidget(pyi)
        pylbl=QLabel("Pan Y"); pylbl.setStyleSheet("font-size:11px;color:#8888a0;border:none;"); pyr.addWidget(pylbl)
        self.pys=QSlider(Qt.Orientation.Horizontal); self.pys.setRange(-100,100); self.pys.setValue(0)
        self.pys.setStyleSheet("QSlider::handle:horizontal{background:#ff8844;border:2px solid #16161f;}"); pyr.addWidget(self.pys, stretch=1)
        self.pyvl=QLabel("0"); self.pyvl.setStyleSheet("font-family:Consolas;font-size:11px;color:#ff8844;min-width:32px;border:none;")
        self.pyvl.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter); pyr.addWidget(self.pyvl)
        self.pys.valueChanged.connect(lambda v: self.pyvl.setText(str(v))); zpl.addLayout(pyr)
        zpr=QHBoxLayout(); zpr.addStretch()
        self.zprb=QPushButton("Reset View"); self.zprb.setFixedHeight(22)
        self.zprb.setStyleSheet("font-size:10px;padding:2px 10px;border:1px solid #2a2a3a;color:#555570;border-radius:4px;")
        def _reset_view(): self.zs.setValue(100); self.pxs.setValue(0); self.pys.setValue(0)
        self.zprb.clicked.connect(_reset_view); zpr.addWidget(self.zprb); zpl.addLayout(zpr)
        ll.addWidget(zpf)

        self.fl=QLabel("-- fps"); self.fl.setStyleSheet("font-family:Consolas;font-size:11px;color:#00ff88;padding:4px 12px;"); ll.addWidget(self.fl)

        ll.addWidget(self._sec("LIVE READINGS"))
        rsa=QScrollArea(); rsa.setWidgetResizable(True); rw=QWidget(); rly=QVBoxLayout(rw); rly.setContentsMargins(8,4,8,4); rly.setSpacing(2)
        for g in GESTURES:
            row=QHBoxLayout(); row.setSpacing(8)
            ic=QLabel(g['icon']); ic.setFixedSize(20,20); ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ic.setStyleSheet(f"background:{g['color']}22;color:{g['color']};border-radius:4px;font-size:11px;"); row.addWidget(ic)
            nm=QLabel(g['name']); nm.setStyleSheet("font-size:11px;color:#8888a0;"); nm.setMinimumWidth(90); row.addWidget(nm); row.addStretch()
            bar=QProgressBar(); bar.setRange(0,100); bar.setTextVisible(False); bar.setFixedWidth(80); bar.setFixedHeight(4)
            bar.setStyleSheet(f"QProgressBar::chunk{{background:{g['color']};border-radius:2px;}}"); row.addWidget(bar); self.rbars[g['id']]=bar
            vl=QLabel("0"); vl.setStyleSheet(f"font-family:Consolas;font-size:11px;color:{g['color']};min-width:28px;")
            vl.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter); row.addWidget(vl); self.rvals[g['id']]=vl
            rly.addLayout(row)
        rsa.setWidget(rw); ll.addWidget(rsa, stretch=1)

        sep=QFrame(); sep.setFrameShape(QFrame.Shape.HLine); sep.setStyleSheet("color:#2a2a3a;"); ll.addWidget(sep)
        ll.addWidget(self._sec("ACTION LOG"))
        self.logl=QLabel("No actions yet"); self.logl.setStyleSheet("font-size:11px;color:#555570;padding:4px 12px;")
        self.logl.setWordWrap(True); self.logl.setMinimumHeight(80); self.logl.setAlignment(Qt.AlignmentFlag.AlignTop); ll.addWidget(self.logl)
        sp.addWidget(left)

        # Right panel
        rsc=QScrollArea(); rsc.setWidgetResizable(True); rwid=QWidget(); rl=QVBoxLayout(rwid); rl.setContentsMargins(20,16,20,60); rl.setSpacing(8)

        # Gesture Chains section
        chain_hdr = QHBoxLayout()
        chain_hdr.addWidget(self._sec("GESTURE CHAINS"))
        chain_hdr.addStretch()
        self.add_chain_btn = QPushButton("\u26A1 Add Gesture Chain")
        self.add_chain_btn.setFixedHeight(28)
        self.add_chain_btn.setStyleSheet("font-size:11px;padding:4px 12px;border:1px solid #ffaa00;color:#ffaa00;border-radius:6px;background:#ffaa0015;font-weight:600;")
        self.add_chain_btn.clicked.connect(self._add_chain)
        chain_hdr.addWidget(self.add_chain_btn)
        self.add_morse_btn = QPushButton("\u2505 Add Morse Chain")
        self.add_morse_btn.setFixedHeight(28)
        self.add_morse_btn.setStyleSheet("font-size:11px;padding:4px 12px;border:1px solid #ff8844;color:#ff8844;border-radius:6px;background:#ff884415;font-weight:600;")
        self.add_morse_btn.clicked.connect(self._add_morse_chain)
        chain_hdr.addWidget(self.add_morse_btn)
        rl.addLayout(chain_hdr)

        self.chains_layout = QVBoxLayout(); self.chains_layout.setContentsMargins(0,0,0,0); self.chains_layout.setSpacing(8)
        rl.addLayout(self.chains_layout)
        self.no_chains_lbl = QLabel("No gesture chains or morse chains defined.")
        self.no_chains_lbl.setStyleSheet("font-size:11px;color:#555570;font-style:italic;padding:8px 0;border:none;")
        self.no_chains_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rl.addWidget(self.no_chains_lbl)

        rl.addWidget(self._sec("EXPRESSION GESTURES"))
        grid=QGridLayout(); grid.setSpacing(10)
        for i,g in enumerate(GESTURES):
            card=GestureCard(g); self.cards[g['id']]=card; grid.addWidget(card, i//2, i%2)
        rl.addLayout(grid)
        # Default: Right Eyebrow Ã¢â€ â€™ The Rock
        for i in range(self.cards['eyebrow_raise_right'].ac.count()):
            if self.cards['eyebrow_raise_right'].ac.itemData(i) == 'the_rock':
                self.cards['eyebrow_raise_right'].ac.setCurrentIndex(i); break

        rl.addWidget(self._sec("GLOBAL SETTINGS"))
        gc=QFrame(); gc.setStyleSheet("background:#16161f;border:1px solid #2a2a3a;border-radius:10px;")
        gcl=QVBoxLayout(gc); gcl.setContentsMargins(14,14,14,14); gcl.setSpacing(6)
        self.sms = self._gslider(gcl,"Smoothing",1,15,9)
        self.cds = self._gslider(gcl,"Cooldown (ms)",50,1500,650,50)
        self.hds = self._gslider(gcl,"Hold Time (ms)",5,500,200,25)
        self.pcs = self._gslider(gcl,"Tilt Compensation",0,100,35)
        rl.addWidget(gc); rl.addStretch()
        rsc.setWidget(rwid); sp.addWidget(rsc); sp.setSizes([320,880]); root.addWidget(sp,stretch=1)

        # Bottom
        bot=QFrame(); bot.setFixedHeight(44); bot.setStyleSheet("background:#12121a;border-top:1px solid #2a2a3a;")
        bl=QHBoxLayout(bot); bl.setContentsMargins(16,0,16,0)
        for txt,fn in [("Export",self._exp),("Import",self._imp),("Reset",self._rst)]:
            b=QPushButton(txt); b.clicked.connect(fn); bl.addWidget(b)
        bl.addStretch()
        self.al=QLabel(f"Active: {len(GESTURES)}/{len(GESTURES)}"); self.al.setStyleSheet("font-family:Consolas;font-size:11px;color:#555570;"); bl.addWidget(self.al)
        self.dl=QLabel("Detections: 0"); self.dl.setStyleSheet("font-family:Consolas;font-size:11px;color:#555570;"); bl.addWidget(self.dl)
        root.addWidget(bot)

    def _sec(self, t):
        l=QLabel(t); l.setStyleSheet("font-family:Consolas;font-size:10px;color:#555570;letter-spacing:1.5px;font-weight:600;padding:8px 12px 4px;"); return l

    def _gslider(self, parent_layout, label, mn, mx, default, step=1):
        h=QHBoxLayout(); l=QLabel(label); l.setStyleSheet("font-size:11px;border:none;"); h.addWidget(l); h.addStretch()
        vl=QLabel(str(default)); vl.setStyleSheet("font-family:Consolas;font-size:11px;color:#555570;border:none;"); h.addWidget(vl)
        parent_layout.addLayout(h)
        sl=QSlider(Qt.Orientation.Horizontal); sl.setRange(mn,mx); sl.setSingleStep(step); sl.setValue(default)
        sl.valueChanged.connect(lambda v: vl.setText(str(v))); parent_layout.addWidget(sl); return sl

    def _set_btn_primary(self):
        self.cb.setStyleSheet("QPushButton{background:#00d4ff;border:1px solid #00d4ff;color:#0a0a0f;font-weight:600;border-radius:6px;padding:6px 16px}QPushButton:hover{background:#00bde6}")
    def _set_btn_danger(self):
        self.cb.setStyleSheet("QPushButton{background:#ff4466;border:1px solid #ff4466;color:#0a0a0f;font-weight:600;border-radius:6px;padding:6px 16px}QPushButton:hover{background:#e63355}")
    def _ss(self, txt, clr):
        self.stl.setText(f"\u25CF {txt}")
        self.stl.setStyleSheet(f"color:{clr};font-family:Consolas;font-size:11px;background:{clr}33;padding:3px 8px;border-radius:10px;border:1px solid {clr};")
    def _tc(self):
        if self.cam and self.cam.isRunning(): self._stop()
        else: self._start()
    def _scan_cameras(self):
        """Scan for available cameras in background thread."""
        cams = enumerate_cameras()
        self._available_cams = cams
        from PyQt6.QtCore import QMetaObject
        QMetaObject.invokeMethod(self, "_populate_cameras", Qt.ConnectionType.QueuedConnection)

    @pyqtSlot()
    def _populate_cameras(self):
        self.cam_cb.clear()
        if not self._available_cams:
            self.cam_cb.addItem("No cameras found", None)
        else:
            for idx, backend, name in self._available_cams:
                self.cam_cb.addItem(f"\U0001F4F7 {name}", (idx, backend))

    def _rescan_cameras(self):
        self.cam_cb.clear()
        self.cam_cb.addItem("Scanning cameras...", None)
        threading.Thread(target=self._scan_cameras, daemon=True).start()

    def _start(self):
        cam_data = self.cam_cb.currentData()
        if cam_data is None:
            self._ss("No camera selected", "#ff4466"); return
        cam_index, cam_backend = cam_data
        self.det.reset(); self.sm={k:0 for k in self.sm}
        self.hold_active={k:False for k in self.hold_active}
        self.toggle_state={k:False for k in self.toggle_state}
        self.repeat_lt={k:0.0 for k in self.repeat_lt}
        self.chain_state={}; self._mc_hs={}; self._mc_buf={}; self._mc_last={}; self._mc_active={}
        self._chain_hs={g['id']:0.0 for g in GESTURES}
        self._chain_ta={g['id']:False for g in GESTURES}; self._chain_newly=set()
        self.cam=CameraThread(cam_index, cam_backend); self.cam.frame_ready.connect(self._of)
        self.cam.status_changed.connect(lambda t: self._ss(t,"#ffaa00"))
        self.cam.error.connect(lambda e: self._ss(e,"#ff4466")); self.cam.start()
        self.cb.setText("\u25A0 Stop Camera"); self._set_btn_danger(); self.rcb.show()
    def _stop(self):
        # Release any held keys/buttons before stopping
        self._release_all_holds()
        if self.cam: self.cam.stop(); self.cam.wait(3000); self.cam=None
        self.cb.setText("\u25B6 Start Camera"); self._set_btn_primary(); self.rcb.hide()
        self._ss("Camera Off","#ff4466"); self.vl.clear(); self.vl.setText("\U0001F4F7  Start Camera"); self.fl.setText("-- fps")
    def _recal(self):
        self._release_all_holds()
        self.chain_state={}
        self.det.reset(); self.sm={k:0 for k in self.sm}; self._ss("Calibrating...","#ffaa00")
    def _release_all_holds(self):
        """Release any keys/buttons currently held by hold or toggle mode."""
        for g in GESTURES:
            gid = g['id']
            if self.hold_active.get(gid, False) or self.toggle_state.get(gid, False):
                s = self.cards[gid].get_state()
                execute_hold_stop(s['action'], s['keyBind'])
                self.hold_active[gid] = False
                self.toggle_state[gid] = False

    @pyqtSlot(object, object, float)
    def _of(self, frame, lm, fps):
        self.fl.setText(f"{fps:.0f} fps")
        d = frame.copy()
        h, w = d.shape[:2]

        # Zoom + pan crop
        zoom = self.zs.value() / 100.0
        pan_x = self.pxs.value() / 100.0
        pan_y = self.pys.value() / 100.0
        crop_w = 1.0 / zoom; crop_h = 1.0 / zoom
        max_off_x = (1.0 - crop_w) / 2.0; max_off_y = (1.0 - crop_h) / 2.0
        cx = 0.5 + pan_x * max_off_x; cy = 0.5 + pan_y * max_off_y
        crop_x0 = cx - crop_w / 2.0; crop_y0 = cy - crop_h / 2.0

        if zoom > 1.0:
            px0 = max(0, min(int(crop_x0 * w), w-1)); py0 = max(0, min(int(crop_y0 * h), h-1))
            px1 = max(1, min(int((crop_x0 + crop_w) * w), w)); py1 = max(1, min(int((crop_y0 + crop_h) * h), h))
            d = cv2.resize(d[py0:py1, px0:px1], (w, h), interpolation=cv2.INTER_LINEAR)

        if lm is not None:
            dh, dw = d.shape[:2]
            for i in range(min(len(lm),468)):
                sx = (lm[i].x - crop_x0) / crop_w; sy = (lm[i].y - crop_y0) / crop_h
                if 0 <= sx <= 1 and 0 <= sy <= 1:
                    cv2.circle(d,(int(sx*dw),int(sy*dh)),1,(255,212,0),-1)
            for idx,clr in [(LEFT_EYE_EAR,(0,255,136)),(RIGHT_EYE_EAR,(0,255,136)),
                            (LEFT_EYEBROW,(0,212,255)),(RIGHT_EYEBROW,(0,212,255)),
                            ([UPPER_LIP,LOWER_LIP,MOUTH_LEFT,MOUTH_RIGHT,LIP_TOP_OUTER,LIP_BOT_OUTER],(255,68,102)),
                            ([MOUTH_CORNER_LEFT,MOUTH_CORNER_RIGHT],(68,221,170)),
                            ([LEFT_BROW_INNER,RIGHT_BROW_INNER],(204,68,255))]:
                for i in idx:
                    if i<len(lm):
                        sx = (lm[i].x - crop_x0) / crop_w; sy = (lm[i].y - crop_y0) / crop_h
                        if 0 <= sx <= 1 and 0 <= sy <= 1:
                            cv2.circle(d,(int(sx*dw),int(sy*dh)),3,clr,-1)
        rgb = cv2.cvtColor(d, cv2.COLOR_BGR2RGB)
        qi = QImage(rgb.data,rgb.shape[1],rgb.shape[0],rgb.strides[0],QImage.Format.Format_RGB888)
        self.vl.setPixmap(QPixmap.fromImage(qi).scaled(self.vl.size(),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))

        if lm is None: self._ss("No Face","#ffaa00"); return
        # Build per-gesture sensitivity dict from card sliders
        sens = {}
        for gid, card in self.cards.items():
            sens[gid] = _sens_mult(card.ss.value())
        raw = self.det.compute(lm, self.pcs.value(), sens=sens)
        if not self.det.calibrated: self._ss(f"Calibrating... ({self.det.cal_pct}%)","#ffaa00"); return
        self._ss("Tracking","#00ff88")

        alpha = 1-(self.sms.value()/15.0)*0.85
        for gid,val in raw.items():
            self.sm[gid]=self.sm.get(gid,0)*(1-alpha)+val*alpha; self.lv[gid]=self.sm[gid]

        for gid in self.lv:
            iv=int(self.lv[gid])
            if gid in self.rbars: self.rbars[gid].setValue(iv)
            if gid in self.rvals: self.rvals[gid].setText(str(iv))
            if gid in self.cards: self.cards[gid].set_live(self.lv[gid])

        cd = self.cds.value(); ht = self.hds.value(); now_ms = time.time()*1000
        REPEAT_INTERVAL = 150  # ms between repeat fires in hold mode for repeatable actions
        for g in GESTURES:
            gid=g['id']; s=self.cards[gid].get_state()
            if not s['enabled']:
                # If disabled mid-hold, release
                if self.hold_active[gid]:
                    execute_hold_stop(s['action'], s['keyBind']); self.hold_active[gid]=False
                continue
            val=self.lv.get(gid,0)
            th = s['thresholdMin']
            mode = s.get('triggerMode', 'single')
            act = s['action']; kb = s['keyBind']; cmd = s['command']; macro = s.get('macro','')

            if val >= th:
                if self.hs[gid] == 0: self.hs[gid] = now_ms
                held = now_ms - self.hs[gid]

                if mode == 'single':
                    # Original behavior: fire once per activation, with cooldown
                    if held >= ht and not self.ta[gid] and now_ms-self.lt[gid]>cd:
                        self.ta[gid]=True; self.lt[gid]=now_ms; self.dc+=1; self.dl.setText(f"Detections: {self.dc}")
                        threading.Thread(target=execute_action,args=(act,kb,cmd,macro),daemon=True).start()
                        self._logit(g['name'],act,kb,macro)

                elif mode == 'hold':
                    # Sustain: press down on activation, release on deactivation
                    if held >= ht and not self.hold_active[gid]:
                        # Start holding
                        self.hold_active[gid] = True; self.ta[gid] = True
                        self.dc+=1; self.dl.setText(f"Detections: {self.dc}")
                        if act in _HOLDABLE_ACTIONS:
                            threading.Thread(target=execute_hold_start,args=(act,kb),daemon=True).start()
                        elif act in _REPEATABLE_ACTIONS or act == 'command':
                            # Fire first shot immediately
                            threading.Thread(target=execute_action,args=(act,kb,cmd,macro),daemon=True).start()
                            self.repeat_lt[gid] = now_ms
                        else:
                            # Non-holdable, non-repeatable: just fire once
                            threading.Thread(target=execute_action,args=(act,kb,cmd,macro),daemon=True).start()
                        self._logit(g['name'],act,kb,macro,mode_tag='HOLD')
                    elif self.hold_active[gid] and act in _REPEATABLE_ACTIONS:
                        # Repeat fire while held
                        if now_ms - self.repeat_lt.get(gid,0) >= REPEAT_INTERVAL:
                            threading.Thread(target=execute_action,args=(act,kb,cmd,macro),daemon=True).start()
                            self.repeat_lt[gid] = now_ms

                elif mode == 'toggle':
                    # Toggle: first activation starts, second stops
                    if held >= ht and not self.ta[gid] and now_ms-self.lt[gid]>cd:
                        self.ta[gid] = True; self.lt[gid] = now_ms
                        self.dc+=1; self.dl.setText(f"Detections: {self.dc}")
                        if not self.toggle_state[gid]:
                            # Toggle ON
                            self.toggle_state[gid] = True
                            if act in _HOLDABLE_ACTIONS:
                                threading.Thread(target=execute_hold_start,args=(act,kb),daemon=True).start()
                            else:
                                threading.Thread(target=execute_action,args=(act,kb,cmd,macro),daemon=True).start()
                            self._logit(g['name'],act,kb,macro,mode_tag='TOG ON')
                        else:
                            # Toggle OFF
                            self.toggle_state[gid] = False
                            if act in _HOLDABLE_ACTIONS:
                                threading.Thread(target=execute_hold_stop,args=(act,kb),daemon=True).start()
                            self._logit(g['name'],act,kb,macro,mode_tag='TOG OFF')
            else:
                # Gesture dropped below threshold
                if mode == 'hold' and self.hold_active[gid]:
                    # Release the held key/button
                    if act in _HOLDABLE_ACTIONS:
                        threading.Thread(target=execute_hold_stop,args=(act,kb),daemon=True).start()
                    self.hold_active[gid] = False
                self.ta[gid]=False; self.hs[gid]=0

        ac=sum(1 for g in GESTURES if self.cards[g['id']].get_state()['enabled'])
        self.al.setText(f"Active: {ac}/{len(GESTURES)}")

        # Ã¢â€â‚¬Ã¢â€â‚¬ Chain sequence detection Ã¢â€â‚¬Ã¢â€â‚¬
        if self.chains:
            ht_chain = self.hds.value()
            # Detect gesture activations for chain matching (works even for disabled individual cards)
            # Use a separate activation tracker so chains work independently
            if not hasattr(self, '_chain_hs'): self._chain_hs = {g['id']:0.0 for g in GESTURES}
            if not hasattr(self, '_chain_ta'): self._chain_ta = {g['id']:False for g in GESTURES}
            if not hasattr(self, '_chain_newly'): self._chain_newly = set()

            self._chain_newly.clear()
            for g in GESTURES:
                gid = g['id']
                val = self.lv.get(gid, 0)
                # Use individual card's threshold even if card is disabled
                card_s = self.cards[gid].get_state()
                th = card_s['thresholdMin']
                if val >= th:
                    if self._chain_hs[gid] == 0: self._chain_hs[gid] = now_ms
                    held = now_ms - self._chain_hs[gid]
                    if held >= ht_chain and not self._chain_ta[gid]:
                        self._chain_ta[gid] = True
                        self._chain_newly.add(gid)  # newly activated this frame
                else:
                    self._chain_ta[gid] = False
                    self._chain_hs[gid] = 0

            # Process each chain
            for chain in self.chains:
                cid = chain.chain_id
                seq = chain.get_gesture_sequence()
                if len(seq) < 2: continue  # need at least 2 gestures for a chain

                if cid not in self.chain_state:
                    self.chain_state[cid] = {'step': 0, 'last_time': 0.0}
                cs = self.chain_state[cid]
                timeout = chain.timeout_sl.value()

                # Check timeout - reset if too long since last step
                if cs['step'] > 0 and (now_ms - cs['last_time']) > timeout:
                    cs['step'] = 0; cs['last_time'] = 0.0

                # Check if expected gesture newly activated
                expected_gid = seq[cs['step']] if cs['step'] < len(seq) else None
                if expected_gid and expected_gid in self._chain_newly:
                    cs['step'] += 1
                    cs['last_time'] = now_ms

                    if cs['step'] >= len(seq):
                        # Chain complete! Fire the action
                        cs['step'] = 0; cs['last_time'] = 0.0
                        a_state = chain.get_action_state()
                        self.dc += 1; self.dl.setText(f"Detections: {self.dc}")
                        threading.Thread(target=execute_action,
                            args=(a_state['action'], a_state['keyBind'], a_state['command'], a_state['macro']),
                            daemon=True).start()
                        chain_name = chain.name_lbl.text()
                        self._logit(f"\u26A1{chain_name}", a_state['action'], a_state['keyBind'], a_state['macro'], mode_tag='CHAIN')

                # Update chain progress indicator
                chain.set_progress(cs['step'], len(seq))


        # -- Morse Chain detection --
        if self.morse_chains:
            if not hasattr(self, '_mc_hs'): self._mc_hs = {}
            if not hasattr(self, '_mc_buf'): self._mc_buf = {}
            if not hasattr(self, '_mc_last'): self._mc_last = {}
            if not hasattr(self, '_mc_active'): self._mc_active = {}
            for chain in self.morse_chains:
                cid = chain.chain_id; gid = chain.gesture_id()
                if not gid: continue
                val = self.lv.get(gid, 0)
                card_s = self.cards[gid].get_state(); th = card_s['thresholdMin']
                short_ms = chain.sh_sl.value(); long_ms = chain.lh_sl.value(); timeout_ms = chain.timeout_sl.value()
                if cid not in self._mc_hs: self._mc_hs[cid] = 0.0
                if cid not in self._mc_buf: self._mc_buf[cid] = []
                if cid not in self._mc_last: self._mc_last[cid] = 0.0
                if cid not in self._mc_active: self._mc_active[cid] = False
                was_active = self._mc_active[cid]; buf = self._mc_buf[cid]
                if not was_active and buf and (now_ms - self._mc_last[cid]) > timeout_ms:
                    self._mc_buf[cid] = []; buf = []; chain.set_progress([], 0.0, False)
                if val >= th:
                    if not was_active: self._mc_hs[cid] = now_ms; self._mc_active[cid] = True
                    held = now_ms - self._mc_hs[cid]
                    if held < short_ms: frac = held / short_ms * 0.5
                    elif held < long_ms: frac = 0.5 + (held - short_ms) / max(1, long_ms - short_ms) * 0.5
                    else: frac = 1.0
                    chain.set_progress(buf, frac, True)
                else:
                    if was_active:
                        self._mc_active[cid] = False; held = now_ms - self._mc_hs[cid]; self._mc_hs[cid] = 0.0
                        if held >= short_ms:
                            sym = 'L' if held >= long_ms else 'S'; buf.append(sym); self._mc_last[cid] = now_ms
                            matched = False
                            for pat, a_state in chain.get_patterns():
                                if buf == pat:
                                    self._mc_buf[cid] = []; buf = []; chain.flash_match()
                                    self.dc += 1; self.dl.setText(f"Detections: {self.dc}")
                                    threading.Thread(target=execute_action,
                                        args=(a_state['action'], a_state['keyBind'], a_state['command'], a_state['macro']),
                                        daemon=True).start()
                                    self._logit(f"\u2505{chain.name_lbl.text()}", a_state['action'], a_state['keyBind'], a_state['macro'], mode_tag='MORSE')
                                    matched = True; break
                            if not matched:
                                is_prefix = any(pat[:len(buf)] == buf for pat, _ in chain.get_patterns())
                                if not is_prefix: self._mc_buf[cid] = []; buf = []
                    chain.set_progress(buf, 0.0, False)

    def _add_chain(self):
        cid = self.chain_counter; self.chain_counter += 1
        chain = GestureChainCard(cid)
        chain.chain_deleted.connect(self._remove_chain)
        chain.gesture_claimed.connect(self._on_gesture_claimed)
        chain.gesture_released.connect(self._on_gesture_released)
        self.chains.append(chain)
        self.chains_layout.addWidget(chain)
        self._update_no_chains_label()

    def _remove_chain(self, chain):
        if chain in self.chains:
            # Release all gestures used by this chain
            for gid in chain.get_all_gesture_ids():
                self._on_gesture_released(gid)
            # Clean up chain state
            if chain.chain_id in self.chain_state:
                del self.chain_state[chain.chain_id]
            self.chains.remove(chain)
            self.chains_layout.removeWidget(chain)
            chain.deleteLater()
            self._update_no_chains_label()

    def _add_morse_chain(self):
        cid = self.chain_counter; self.chain_counter += 1
        chain = MorseChainCard(cid)
        chain.chain_deleted.connect(self._remove_morse_chain)
        chain.gesture_claimed.connect(self._on_gesture_claimed)
        chain.gesture_released.connect(self._on_gesture_released)
        chain.connect_reset(lambda cid=cid: self._reset_morse_chain(cid))
        self.morse_chains.append(chain)
        self.chains_layout.addWidget(chain)
        self._update_no_chains_label()

    def _remove_morse_chain(self, chain):
        if chain in self.morse_chains:
            for gid in chain.get_all_gesture_ids():
                self._on_gesture_released(gid)
            cid = chain.chain_id
            for d in (getattr(self, '_mc_hs', {}), getattr(self, '_mc_buf', {}),
                      getattr(self, '_mc_last', {}), getattr(self, '_mc_active', {})):
                d.pop(cid, None)
            self.morse_chains.remove(chain)
            self.chains_layout.removeWidget(chain)
            chain.deleteLater()
            self._update_no_chains_label()

    def _reset_morse_chain(self, cid):
        for d in (getattr(self, '_mc_buf', {}), getattr(self, '_mc_hs', {}),
                  getattr(self, '_mc_last', {}), getattr(self, '_mc_active', {})):
            if cid in d:
                if isinstance(d[cid], list): d[cid] = []
                else: d[cid] = 0.0 if isinstance(d[cid], float) else False
        for chain in self.morse_chains:
            if chain.chain_id == cid: chain.set_progress([], 0.0, False); break

    def _on_gesture_claimed(self, gid):
        """A chain claimed a gesture - disable its individual card."""
        if gid in self.cards:
            self.cards[gid].en.setChecked(False)

    def _on_gesture_released(self, gid):
        """A chain released a gesture - re-enable if no other chain uses it."""
        if not gid: return
        for chain in self.chains:
            if gid in chain.get_all_gesture_ids(): return
        for chain in self.morse_chains:
            if gid in chain.get_all_gesture_ids(): return
        if gid in self.cards:
            self.cards[gid].en.setChecked(True)

    def _update_no_chains_label(self):
        self.no_chains_lbl.setVisible(len(self.chains) == 0 and len(self.morse_chains) == 0)

    def _logit(self,gn,at,kb='',macro='',mode_tag=''):
        ts=datetime.now().strftime('%H:%M:%S')
        if at=='none': return
        if at=='key': desc=f"Key: {kb}"
        elif at=='macro': desc=f"Macro: {macro[:30]}"
        else: desc=at
        if mode_tag: desc=f"[{mode_tag}] {desc}"
        self.alog.appendleft(f'<span style="color:#555570;">{ts}</span> <span style="color:#00d4ff;">{gn}</span> \u2192 <span style="color:#00ff88;">{desc} \u2714</span>')
        self.logl.setText('<br>'.join(list(self.alog)[:8]))

    def _exp(self):
        cfg={'version':'0.5.0','gestures':{gid:c.get_state() for gid,c in self.cards.items()},
             'chains':[c.get_state() for c in self.chains],
             'morse_chains':[c.get_state() for c in self.morse_chains],
             'global':{'smoothing':self.sms.value(),'cooldown':self.cds.value(),'holdTime':self.hds.value(),'tiltComp':self.pcs.value(),'zoom':self.zs.value(),'panX':self.pxs.value(),'panY':self.pys.value()}}
        p,_=QFileDialog.getSaveFileName(self,"Export","gestures_config.json","JSON (*.json)")
        if p:
            with open(p,'w') as f: json.dump(cfg,f,indent=2)

    def _imp(self):
        p,_=QFileDialog.getOpenFileName(self,"Import","","JSON (*.json)")
        if not p: return
        try:
            with open(p) as f: cfg=json.load(f)
            if 'gestures' in cfg:
                for gid,s in cfg['gestures'].items():
                    if gid in self.cards: self.cards[gid].set_state(s)
            # Remove existing chains first
            for ch in list(self.chains): self._remove_chain(ch)
            for ch in list(self.morse_chains): self._remove_morse_chain(ch)
            if 'chains' in cfg:
                for cs in cfg['chains']:
                    self._add_chain()
                    self.chains[-1].set_state(cs)
            if 'morse_chains' in cfg:
                for cs in cfg['morse_chains']:
                    self._add_morse_chain()
                    self.morse_chains[-1].set_state(cs)
            if 'global' in cfg:
                g=cfg['global']; self.sms.setValue(g.get('smoothing',9))
                self.cds.setValue(g.get('cooldown',650)); self.hds.setValue(g.get('holdTime',200))
                self.pcs.setValue(g.get('tiltComp',35)); self.zs.setValue(g.get('zoom',100))
                self.pxs.setValue(g.get('panX',0)); self.pys.setValue(g.get('panY',0))
        except Exception as e: print(f"Import error: {e}")

    def _rst(self):
        # Remove all chains
        for ch in list(self.chains): self._remove_chain(ch)
        for ch in list(self.morse_chains): self._remove_morse_chain(ch)
        for c in self.cards.values(): c.reset_def()
        self.sms.setValue(9); self.cds.setValue(650); self.hds.setValue(200); self.pcs.setValue(35)
        self.zs.setValue(100); self.pxs.setValue(0); self.pys.setValue(0)

    def closeEvent(self,e): self._release_all_holds(); self._stop(); e.accept()

# ÃƒÂ¢Ã¢â‚¬Â¢Ã‚ÂÃƒÂ¢Ã¢â‚¬Â¢Ã‚ÂÃƒÂ¢Ã¢â‚¬Â¢Ã‚Â ENTRY ÃƒÂ¢Ã¢â‚¬Â¢Ã‚ÂÃƒÂ¢Ã¢â‚¬Â¢Ã‚ÂÃƒÂ¢Ã¢â‚¬Â¢Ã‚Â

if __name__ == '__main__':
    try:
        app=QApplication(sys.argv); app.setStyleSheet(SS)
        w=MainWindow(); w.show(); sys.exit(app.exec())
    except Exception:
        import traceback; traceback.print_exc()
        print("\nPress Enter..."); input()
