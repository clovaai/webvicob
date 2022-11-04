"""
WEBVICOB
Copyright 2022-present NAVER Corp.
Apache-2.0
"""
import json
import os
from pathlib import Path

import cv2
import lmdb
import numpy as np

LMDB_MAP_SIZE = 10 * 1024 ** 4  # 10 TiB
COMMIT_INTERVAL = 100


class WebvicobLMDB:
    def __init__(self, lmdb_path: Path, readonly=False, verbose=True):
        lmdb_path.parent.mkdir(parents=True, exist_ok=True)
        self.lmdb_path = str(lmdb_path)
        self.env = lmdb.open(self.lmdb_path, map_size=LMDB_MAP_SIZE, readonly=readonly)
        os.system(f"chmod -R 777 {self.lmdb_path}")
        self.verbose = verbose

        if verbose:
            print(f"{self.lmdb_path} LMDB_DUMP started.")

    def get(self, key):
        with self.env.begin(write=False) as txn:
            value = txn.get(key)
        return value

    def get_raw_html(self, idx):
        return decode(self.get(encode(f"{idx}_raw_html")))

    def get_html(self, idx):
        return decode(self.get(encode(f"{idx}_html")))

    def get_img(self, idx):
        jpeg_read = self.get(encode(f"{idx}_img"))
        jpeg_read = np.frombuffer(jpeg_read, dtype=np.uint8)
        img = cv2.imdecode(jpeg_read, cv2.IMREAD_COLOR)
        return img

    def get_annots(self, idx):
        annots = self.get(encode(f"{idx}_annots"))
        annots = json.loads(decode(annots))
        return annots

    def get_num_data(self):
        return int(self.get("num_data".encode()).decode())

    def put(self, key, value):
        with self.env.begin(write=True) as txn:
            txn.put(key, value)

    def put_raw_html(self, raw_html, idx):
        self.put(encode(f"{idx}_raw_html"), encode(raw_html))

    def put_html(self, html, idx):
        self.put(encode(f"{idx}_html"), encode(html))

    def put_img(self, img_buffer, idx):
        self.put(encode(f"{idx}_img"), img_buffer)

    def put_annots(self, annots, idx):
        self.put(
            encode(f"{idx}_annots"), encode(json.dumps(annots, ensure_ascii=False))
        )

    def put_num_data(self, num_data):
        self.put(encode("num_data"), encode(str(num_data)))

    def wrap_up(self):
        if self.verbose:
            print(f"{self.lmdb_path} LMDB_DUMPED. NUM_DATA: {self.get_num_data()}")
        self.env.close()


def encode(string_data):
    return string_data.encode("utf-8")


def decode(string_data):
    return string_data.decode("utf-8")
