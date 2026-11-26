#!/usr/bin/env python3
"""Отдаёт только HTML-макет (без Vite/TSX). Запуск: python3 serve-mockup.py"""
from __future__ import annotations

import http.server
import os
import socketserver

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mockup")
PORT = int(os.environ.get("PORT", "8765"))


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)


def main() -> None:
    os.chdir(ROOT)
    with socketserver.TCPServer(("0.0.0.0", PORT), Handler) as httpd:
        print(f"Beaty-Welcome mockup: http://127.0.0.1:{PORT}/index.html")
        print(f"Serving directory: {ROOT}")
        httpd.serve_forever()


if __name__ == "__main__":
    main()