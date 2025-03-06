from flask import Flask
from threading import Thread
import logging

app = Flask('')
logging.getLogger('werkzeug').setLevel(logging.ERROR)  # Reduce Flask logging noise

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    try:
        app.run(host='0.0.0.0', port=5000)
    except Exception as e:
        print(f"Error starting keep-alive server: {e}")

def keep_alive():
    server_thread = Thread(target=run)
    server_thread.daemon = True  # Thread will exit when main program exits
    server_thread.start()