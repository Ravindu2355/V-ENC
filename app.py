from flask import Flask, jsonify, request
import os
from flask_cors import CORS
from threading import Thread

app = Flask(__name__)

CORS(app)

@app.route('/')
def hello_world():
    return 'Hello from Koyeb'


if __name__ == "__main__":
    app.run(host='0.0.0.0',port=8000)
