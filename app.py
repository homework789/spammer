# app.py
from flask import Flask, render_template_string, request, jsonify
import requests
import threading
import time
import random
import string
import os
import re

app = Flask(__name__)

running = False
stats = {"sent": 0, "zombies": 0}
lock = threading.Lock()

HTML = """
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>tlk.io Panel</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: #0f1115;
    color: #e1e4e8;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    font-size: 14px;
    line-height: 1.5;
    padding: 24px;
    max-width: 480px;
    margin: 0 auto;
  }
  h1 {
    font-size: 18px;
    font-weight: 600;
    margin-bottom: 20px;
    color: #fff;
  }
  label {
    display: block;
    font-size: 12px;
    color: #8b949e;
    margin-bottom: 4px;
    margin-top: 12px;
  }
  input, textarea {
    width: 100%;
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 6px;
    color: #e1e4e8;
    padding: 8px 10px;
    font-size: 13px;
  }
  input:focus, textarea:focus {
    outline: none;
    border-color: #58a6ff;
  }
  textarea { resize: vertical; min-height: 90px; }
  .row {
    display: flex;
    gap: 10px;
  }
  .row > div { flex: 1; }
  .btns {
    display: flex;
    gap: 8px;
    margin-top: 16px;
  }
  button {
    flex: 1;
    border: none;
    border-radius: 6px;
    padding: 10px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
  }
  #start {
    background: #238636;
    color: #fff;
  }
  #start:hover { background: #2ea043; }
  #stop {
    background: #21262d;
    color: #f85149;
    border: 1px solid #30363d;
  }
  #stop:hover { background: #30363d; }
  .stats {
    margin-top: 16px;
    font-size: 13px;
    color: #8b949e;
  }
  .stats b { color: #e1e4e8; }
  #log {
    margin-top: 12px;
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 6px;
    height: 180px;
    overflow-y: auto;
    padding: 10px;
    font-size: 12px;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    color: #8b949e;
  }
</style>
</head>
<body>
  <h1>tlk.io Panel</h1>

  <label>Channel</label>
  <input id="channel" value="523unji" placeholder="channel name">

  <label>Messages (one per line)</label>
  <textarea id="msgs">hello
test
spam</textarea>

  <div class="row">
    <div>
      <label>Threads</label>
      <input id="threads" type="number" value="20">
    </div>
    <div>
      <label>Delay (ms)</label>
      <input id="delay" type="number" value="60">
    </div>
  </div>

  <div class="btns">
    <button id="start" onclick="start()">Start</button>
    <button id="stop" onclick="stop()">Stop</button>
  </div>

  <div class="stats">
    Sent: <b id="sent">0</b> &nbsp;|&nbsp; Active: <b id="zombies">0</b>
  </div>
  <div id="log"></div>

<script>
function log(t) {
  const el = document.getElementById('log');
  el.innerHTML += t + '<br>';
  el.scrollTop = el.scrollHeight;
}
function start() {
  const body = {
    channel: document.getElementById('channel').value.trim(),
    messages: document.getElementById('msgs').value.split('\\n').filter(x => x.trim()),
    threads: parseInt(document.getElementById('threads').value) || 10,
    delay: parseInt(document.getElementById('delay').value) || 60
  };
  fetch('/start', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body)
  }).then(r => r.json()).then(d => log(d.msg));
}
function stop() {
  fetch('/stop').then(r => r.json()).then(d => log(d.msg));
}
setInterval(() => {
  fetch('/stats').then(r => r.json()).then(d => {
    document.getElementById('sent').textContent = d.sent;
    document.getElementById('zombies').textContent = d.zombies;
  });
}, 500);
</script>
</body>
</html>
"""

def random_nick():
    return random.choice(["u", "x", "n", "z", "a"]) + "".join(random.choices(string.ascii_lowercase + string.digits, k=5))

def get_chat_id(channel):
    try:
        r = requests.get(f"https://tlk.io/{channel}", timeout=8)
        m = re.search(r'/api/chats/(\d+)/messages', r.text)
        if m:
            return m.group(1)
        m = re.search(r'chats/(\d+)', r.text)
        if m:
            return m.group(1)
    except:
        pass
    return None

def worker(chat_id, messages, delay_ms):
    global running, stats
    nick = random_nick()
    with lock:
        stats["zombies"] += 1
    session = requests.Session()
    try:
        r = session.post("https://tlk.io/api/participant",
                         json={"nickname": nick}, timeout=6)
        if r.status_code != 200:
            with lock:
                stats["zombies"] -= 1
            return

        while running:
            try:
                msg = random.choice(messages)
                resp = session.post(
                    f"https://tlk.io/api/chats/{chat_id}/messages",
                    json={"body": msg, "nickname": nick},
                    timeout=4
                )
                if resp.status_code == 200:
                    with lock:
                        stats["sent"] += 1
                time.sleep(max(0.03, delay_ms / 1000.0))
            except:
                time.sleep(0.3)
    finally:
        with lock:
            stats["zombies"] -= 1

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/start", methods=["POST"])
def start():
    global running
    if running:
        return jsonify({"msg": "already running"})
    data = request.json
    channel = (data.get("channel") or "").strip()
    messages = data.get("messages") or ["."]
    threads = min(40, max(1, int(data.get("threads", 15))))
    delay = max(30, int(data.get("delay", 60)))

    chat_id = get_chat_id(channel)
    if not chat_id:
        return jsonify({"msg": f"cannot find chat_id for '{channel}'"})

    running = True
    for _ in range(threads):
        t = threading.Thread(target=worker, args=(chat_id, messages, delay), daemon=True)
        t.start()
        time.sleep(0.02)
    return jsonify({"msg": f"started {threads} threads | chat_id={chat_id} | {delay}ms"})

@app.route("/stop")
def stop():
    global running
    running = False
    return jsonify({"msg": "stopped"})

@app.route("/stats")
def get_stats():
    return jsonify(stats)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)