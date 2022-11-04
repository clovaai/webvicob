"""
WEBVICOB
Copyright 2022-present NAVER Corp.
Apache-2.0
"""
import copy
import json
import math
import multiprocessing as mp
import os
import pickle
import random
import re
import time
import traceback
import unicodedata
from base64 import b64decode
from collections import defaultdict
from copy import deepcopy
from multiprocessing.shared_memory import SharedMemory
from pathlib import Path
from pprint import pprint
from typing import List, Optional
from uuid import uuid4

import cv2
import fire
import numpy as np
from bs4 import BeautifulSoup, element
from matplotlib import cm
from pygame import freetype
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

from webvicob.lmdb_maker import WebvicobLMDB
from webvicob.shrinkbox import shrinkbox

semaphore = mp.Semaphore(100)
base_font_path = Path("font/google/ofl/notosans/NotoSans-Regular.ttf").resolve()


def main(
    workspace="./",
    target_lang="ja",
    num_train=-1,
    num_val=0,
    num_test=0,
    debug=False,
    num_process=-1,
    shrink_heuristic=True,
    remove_background=True,
    unroll_contents=False,
    change_para_font=True,
    sleep_time=1,
    capture_widths=(800, 1200, 1600),
    capture_height_limit=16384,
    final_width=None,
    chunk_idx=None,
    total_chunk=None,
    chrome_path="resources/chromedriver_linux64_103.0.5060.24",
):
    assert capture_height_limit < 32760  # opencv limit
    if num_process == -1:
        num_process = os.cpu_count()
    if debug:
        num_process = 1

    workspace = Path(workspace)
    font_paths = get_font_paths(debug)

    opt = {
        "debug": debug,
        "shrink_heuristic": shrink_heuristic,
        "remove_background": remove_background,
        "unroll_contents": unroll_contents,
        "change_para_font": change_para_font,
        "js_font_paths": ["file:///" + path for path in font_paths],
        "sleep_time": sleep_time,
        "capture_widths": capture_widths,
        "capture_height_limit": capture_height_limit,
        "target_lang": target_lang,
        "final_width": final_width,
        "chrome_path": chrome_path,
    }
    pprint(opt)

    pickled_opt = bytearray(pickle.dumps(opt))
    shm_name = f"webvicob_wikipedia_{uuid4()}"
    shm = SharedMemory(create=True, size=len(pickled_opt), name=shm_name)
    shm.buf[:] = pickled_opt
    shm.close()

    if num_train == -1:
        num_total_data = get_total_size(workspace, target_lang, chunk_idx, total_chunk)
        num_train = num_total_data - num_val - num_test
    else:
        num_total_data = num_train + num_val + num_test

    ver_str = get_version_str(target_lang, num_train, chunk_idx)
    print(f"VER_STR: {ver_str}", flush=True)
    webvicob_lmdbs = {
        mode: WebvicobLMDB(workspace / ver_str / mode, verbose=False)
        for mode in ("train", "val", "test")
    }
    data_counter = {"total": 0, "train": 0, "val": 0, "test": 0}

    if debug:
        counter = 0
        for inp in html_generator(
            workspace, target_lang, shm_name, chunk_idx, total_chunk
        ):
            counter += 1
            if counter < 5:
                continue
            html, modified_html, jpeg, annots = mp_job(inp)
            if html == "keyboard interrupt":
                break
            if html == "None":
                print("Failed to capture.")
                continue

            if data_counter["total"] < num_val:
                mode = "val"
            elif num_val <= data_counter["total"] < num_test + num_val:
                mode = "test"
            else:
                mode = "train"
            webvicob_lmdb = webvicob_lmdbs[mode]

            webvicob_lmdb.put_raw_html(html, data_counter[mode])
            webvicob_lmdb.put_html(modified_html, data_counter[mode])
            webvicob_lmdb.put_img(jpeg, data_counter[mode])
            webvicob_lmdb.put_annots(annots, data_counter[mode])

            data_counter[mode] += 1
            data_counter["total"] += 1
            print(f"[{data_counter['total']} / {num_total_data}] processed.")

            if data_counter["total"] == num_total_data:
                break
    else:
        with mp.Pool(num_process) as pool:
            for html, modified_html, jpeg, annots in pool.imap_unordered(
                mp_job,
                html_generator(
                    workspace, target_lang, shm_name, chunk_idx, total_chunk
                ),
            ):
                if html == "keyboard interrupt":
                    break
                if html == "None":
                    print("Failed to capture.")
                    continue

                if data_counter["total"] < num_val:
                    mode = "val"
                elif num_val <= data_counter["total"] < num_test + num_val:
                    mode = "test"
                else:
                    mode = "train"
                webvicob_lmdb = webvicob_lmdbs[mode]

                webvicob_lmdb.put_raw_html(html, data_counter[mode])
                webvicob_lmdb.put_html(modified_html, data_counter[mode])
                webvicob_lmdb.put_img(jpeg, data_counter[mode])
                webvicob_lmdb.put_annots(annots, data_counter[mode])

                data_counter[mode] += 1
                data_counter["total"] += 1

                if data_counter["total"] % 1000 == 0:
                    print(f"[{data_counter['total']} / {num_total_data}] processed.")

                if data_counter["total"] == num_total_data:
                    break

    for mode, webvicob_lmdb in webvicob_lmdbs.items():
        webvicob_lmdb.put_num_data(data_counter[mode])

    if debug:
        for mode, webvicob_lmdb in webvicob_lmdbs.items():
            num_data = webvicob_lmdb.get_num_data()
            for i in range(num_data):
                img = webvicob_lmdb.get_img(i)
                annots = webvicob_lmdb.get_annots(i)
                visualize(img, annots, save=True, idx=i, max_hw=1600)

    shm.unlink()
    for mode, webvicob_lmdb in webvicob_lmdbs.items():
        webvicob_lmdb.wrap_up()


def get_font_paths(debug):
    font_paths = []
    for p in Path("font/google").glob("**/*.ttf"):
        font_path = str(p.resolve())
        font_paths.append(font_path)

    print(f"total detected fonts: {len(font_paths)}")

    if debug:
        print("Debug mode only use first 10 fonts for low memory usage.")
        font_paths = font_paths[:10]

    return font_paths


def get_total_size(workspace, target_lang, chunk_idx, total_chunk):
    original_data_path = workspace / "raw"
    jsonl_paths = get_jsonl_paths(original_data_path, target_lang)
    if chunk_idx is not None and total_chunk is not None:
        jsonl_paths = np.array_split(jsonl_paths, total_chunk)[chunk_idx]

    total_size = 0
    for jsonl_path in jsonl_paths:
        reader = JsonlReader(jsonl_path)
        total_size += reader.jsonl_size
        del reader
    return total_size


def html_generator(workspace, target_lang, shm_name, chunk_idx, total_chunk):
    original_data_path = workspace / "raw"
    jsonl_paths = get_jsonl_paths(original_data_path, target_lang)
    if chunk_idx is not None and total_chunk is not None:
        jsonl_paths = np.array_split(jsonl_paths, total_chunk)[chunk_idx]

    for jsonl_path in jsonl_paths:
        reader = JsonlReader(jsonl_path)
        for i in range(reader.jsonl_size):
            html = reader.read_jsonl(i)["article_body"]["html"]
            html = replace_html(html, target_lang)
            semaphore.acquire()
            yield {"html": html, "shm_name": shm_name}


def replace_html(html, target_lang):
    wiki_url = f"https://{target_lang}.wikipedia.org"
    html = html.replace('href="//', 'href="https://')
    html = html.replace('src="//', 'src="https://')
    html = html.replace('href="/', f'href="{wiki_url}/')
    html = html.replace('src="/', f'src="{wiki_url}/')
    html = html.replace("//upload.wikimedia", "https://upload.wikimedia")
    html = html.replace(":url('//", ":url('https://")
    html = html.replace(":url('/", f":url('{wiki_url}/")

    def _regex_srcset_handler(m):
        _matched_str = m.group(1)
        _https_added = []
        for _str in _matched_str.split(", "):
            if _str.startswith("//"):
                _https_added.append("https:" + _str)
            elif _str.startswith("/"):
                _https_added.append(wiki_url + _str)
            else:
                _https_added.append(_str)
        _https_added = ", ".join(_https_added)
        return 'srcset="' + _https_added + '"'

    html = re.sub(r'srcset="(.+?)"', _regex_srcset_handler, html)
    html = re.sub(r"(https:)+https://", "https://", html)
    return html


def get_jsonl_paths(original_data_path, target_lang):
    jsonl_paths = []
    for path in original_data_path.iterdir():
        if path.suffix == ".ndjson" and str(path.name).startswith(f"{target_lang}wiki"):
            jsonl_paths.append(path)
    jsonl_paths = list(sorted(jsonl_paths))
    pprint(f"jsonl_paths: {jsonl_paths}")
    return jsonl_paths


class JsonlReader:
    def __init__(self, jsonl_file_path):
        self.jsonl_file_path = jsonl_file_path
        self.offsets = [0]
        self.jsonl_size = 0

        with open(self.jsonl_file_path, "r", encoding="utf-8") as f:
            while f.readline():
                self.offsets.append(f.tell())
                self.jsonl_size += 1

    def read_jsonl(self, idx):
        with open(self.jsonl_file_path, "r", encoding="utf-8") as f:
            f.seek(self.offsets[idx])
            line = f.readline()
            json_data = json.loads(line)
        return json_data


def get_driver(chrome_path, headless=True, capture_width=1600):
    """
    Get google chrome driver.

    # for chromium options
    # https://peter.sh/experiments/chromium-command-line-switches/
    # https://chromium.googlesource.com/chromium/src/+/refs/heads/main/chrome/common/pref_names.cc
    """
    os.environ["WDM_LOG"] = "0"
    service = Service(chrome_path)

    options = webdriver.ChromeOptions()
    options.add_argument("disable-application-cache")
    options.add_argument("disk-cache-size=2147483648")  # 2GB
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument(f"--window-size={capture_width},100")
    options.add_argument("--hide-scrollbars")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_experimental_option(
        "prefs", {"profile.default_content_settings.popups": 0}
    )
    if headless:
        options.add_argument("--headless")

    driver = webdriver.Chrome(service=service, options=options)
    driver.timeouts._script = 180
    driver.implicitly_wait(60)
    return driver


def mp_job(inp):
    semaphore.release()
    try:
        shm = SharedMemory(name=inp["shm_name"])
        opt = pickle.loads(bytes(shm.buf[:]))
        capture_width = random.choice(opt["capture_widths"])

        driver = get_driver(chrome_path=opt["chrome_path"], headless=True, capture_width=capture_width)
        modified_html = modify_html(inp["html"])
        load_html(driver, modified_html, f"tmp_{uuid4()}.html")

        # For faster decision. This also prevents OOM error.
        # Should be called once more in `capture()` since the page height will be
        # changed after execute js scripts.
        page_rect = driver.execute_cdp_cmd("Page.getLayoutMetrics", {})
        capture_height = page_rect["cssContentSize"]["height"] + 50
        if capture_height >= opt["capture_height_limit"]:
            print(f"image height {capture_height} is too big to capture.", flush=True)
            return "None", "None", "None", "None"

        font2path = execute_js(
            driver,
            opt["remove_background"],
            opt["unroll_contents"],
            opt["change_para_font"],
            opt["js_font_paths"],
        )
        time.sleep(opt["sleep_time"])
        boxes = get_boxes(driver)
        jpeg = capture(driver, capture_width, opt["capture_height_limit"])
        driver.close()
        driver.quit()
        if jpeg is None:
            return "None", "None", "None", "None"
        annots = create_annotation(
            jpeg, boxes, font2path, opt["shrink_heuristic"], opt["target_lang"]
        )
        annots["capture_width"] = capture_width

        if opt["final_width"] is not None:
            jpeg, annots = resize_to_final_width(
                jpeg, annots, opt["final_width"], capture_width
            )
    except KeyboardInterrupt:
        print("Keyboard interrupted. Shutting down ...")
        return "keyboard interrupt", "None", "None", "None"

    except:
        print(traceback.format_exc(), flush=True)
        return "None", "None", "None", "None"

    return inp["html"], modified_html, jpeg, annots


def resize_to_final_width(jpeg, annots, final_width, capture_width):
    buffer = np.frombuffer(jpeg, dtype=np.uint8)
    img = cv2.imdecode(buffer, cv2.IMREAD_COLOR)

    ratio = final_width / capture_width
    img = cv2.resize(img, None, fx=ratio, fy=ratio, interpolation=cv2.INTER_CUBIC)
    for line in annots["lines"]:
        line["bbox"] = [val * ratio for val in line["bbox"]]
        for word in line["words"]:
            word["bbox"] = [val * ratio for val in word["bbox"]]
            if word["chars"] is not None:
                for char in word["chars"]:
                    char["bbox"] = [val * ratio for val in char["bbox"]]

    for image_annot in annots["images"]:
        image_annot["bbox"] = [val * ratio for val in image_annot["bbox"]]

    for para in annots["paragraphs"]:
        para["poly"] = [val * ratio for val in para["poly"]]

    for table in annots["tables"]:
        table["bbox"] = [val * ratio for val in table["bbox"]]

    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 95]
    _, jpeg = cv2.imencode(".jpg", img, encode_param)

    return jpeg, annots


def modify_html(html):
    html = add_boxes(html)
    return html


def execute_js(
    driver, remove_background, unroll_contents, change_para_font, js_font_paths
):
    update_invisible_element_priority(driver)
    remove_element(driver, "label")
    remove_pseudo_element(driver)
    remove_border_bottom(driver)
    if change_para_font:
        font2path = change_paragraph_fonts(driver, js_font_paths=js_font_paths)
    else:
        font2path = {}

    if remove_background:
        remove_background_image(driver)
    if unroll_contents:
        remove_position(driver)
        remove_float(driver)
        remove_flexbox(driver)

    return font2path


def load_html(driver, html, tmp_path, unlink=True):
    tmp_file = Path(tmp_path)
    tmp_file.write_text(html)
    driver.get(f"file://{str(tmp_file.resolve())}")
    if unlink:
        tmp_file.unlink()


def capture(driver, capture_width, capture_height_limit):
    driver.execute_cdp_cmd(
        "Runtime.setMaxCallStackSizeToCapture", {"size": 2 ** 31 - 1}
    )
    page_rect = driver.execute_cdp_cmd("Page.getLayoutMetrics", {})
    capture_h = page_rect["cssContentSize"]["height"] + 50
    if capture_h >= capture_height_limit:
        print(f"image height {capture_h} is too big to capture.", flush=True)
        return None

    img_data = driver.execute_cdp_cmd(
        "Page.captureScreenshot",
        {
            "format": "jpeg",
            "quality": 95,
            "captureBeyondViewport": True,
            "fromSurface": True,
            "clip": {
                "width": capture_width,
                "height": capture_h,
                "x": 0,
                "y": 0,
                "scale": 1,
            },
        },
    )
    if img_data is None:
        return None

    jpeg = b64decode(img_data["data"].encode("ascii"))
    return jpeg


def visualize(img, annots, save=False, idx=0, max_hw=1600):
    image_char = visualize_char(img, annots, max_hw=max_hw)
    image_images = visualize_images(img, annots, max_hw=max_hw)
    image_paras = visualize_paras(img, annots, max_hw=max_hw)
    image_tables = visualize_tables(img, annots, max_hw=max_hw)
    image_line = visualize_line(img, annots, max_hw=max_hw)
    image_words_wo_latex = visualize_words_wo_latex(img, annots, max_hw=max_hw)
    image_latex = visualize_latex(img, annots, max_hw=max_hw)

    if save:
        cv2.imwrite(f"char_{idx}.jpg", image_char)
        cv2.imwrite(f"images_{idx}.jpg", image_images)
        cv2.imwrite(f"paragraphs_{idx}.jpg", image_paras)
        cv2.imwrite(f"tables_{idx}.jpg", image_tables)
        cv2.imwrite(f"line_{idx}.jpg", image_line)
        cv2.imwrite(f"words_wo_latex_{idx}.jpg", image_words_wo_latex)
        cv2.imwrite(f"latex_{idx}.jpg", image_latex)
    else:
        cv2.imshow(f"char", image_char)
        cv2.imshow(f"images", image_images)
        cv2.imshow(f"paragraphs", image_paras)
        cv2.imshow(f"tables", image_tables)
        cv2.imshow(f"line", image_line)
        cv2.imshow(f"words_wo_latex", image_words_wo_latex)
        cv2.imshow(f"latex", image_latex)
        cv2.waitKey(0)


def visualize_char(image, annots, max_hw=None):
    boxes = []
    for line in annots["lines"]:
        for word in line["words"]:
            if word["chars"] is not None:
                for char in word["chars"]:
                    boxes.append(char)

    image = draw_rectangle(image, boxes, max_hw)
    return image


def visualize_images(image, annots, max_hw=None):
    boxes = []
    for image_annot in annots["images"]:
        boxes.append(image_annot)

    image = draw_rectangle(image, boxes, max_hw)
    return image


def visualize_paras(image, annots, max_hw=None):
    boxes = []
    for para in annots["paragraphs"]:
        boxes.append(para)

    image = np.copy(image)
    cmap = cm.get_cmap("jet")

    for idx, box in enumerate(boxes):
        value = 1 - (idx / (len(boxes) - 1) if len(boxes) > 1 else 0)
        color = np.array(cmap(value))[[2, 1, 0, 3]] * 255
        poly = np.array(box["poly"], dtype=np.int32).reshape((1, -1, 2))
        image = cv2.polylines(image, poly, True, color, 1)

    img_maxlen = max(image.shape[:2])
    if max_hw is not None and img_maxlen > max_hw:
        ratio = max_hw / img_maxlen
        image = cv2.resize(image, dsize=(0, 0), fx=ratio, fy=ratio)
    return image


def visualize_tables(image, annots, max_hw=None):
    boxes = []
    for table in annots["tables"]:
        boxes.append(table)

    image = draw_rectangle(image, boxes, max_hw)
    return image


def visualize_line(image, annots, max_hw=None):
    boxes = []
    for line in annots["lines"]:
        boxes.append(line)

    image = draw_rectangle(image, boxes, max_hw)
    return image


def visualize_words_wo_latex(image, annots, max_hw=None):
    boxes = []
    for line in annots["lines"]:
        for word in line["words"]:
            if not word["is_latex"]:
                boxes.append(word)

    image = draw_rectangle(image, boxes, max_hw)
    return image


def visualize_latex(image, annots, max_hw=None):
    boxes = []
    for line in annots["lines"]:
        for word in line["words"]:
            if word["is_latex"]:
                boxes.append(word)
    image = draw_rectangle(image, boxes, max_hw)
    return image


def draw_rectangle(image, boxes, max_hw=None):
    image = np.copy(image)
    cmap = cm.get_cmap("jet")

    for idx, box in enumerate(boxes):
        value = 1 - (idx / (len(boxes) - 1) if len(boxes) > 1 else 0)
        color = np.array(cmap(value))[[2, 1, 0, 3]] * 255
        image = cv2.rectangle(
            image,
            (round(box["bbox"][0]), round(box["bbox"][1])),
            (round(box["bbox"][2]), round(box["bbox"][3])),
            color,
            1,
        )

    img_maxlen = max(image.shape[:2])
    if max_hw is not None and img_maxlen > max_hw:
        ratio = max_hw / img_maxlen
        image = cv2.resize(image, dsize=(0, 0), fx=ratio, fy=ratio)
    return image


def add_boxes(html):
    def _add_boxes(soup, elem):
        if isinstance(elem, element.NavigableString):
            tags = []

            for char in elem.text:
                # ignore control character
                category = unicodedata.category(char)
                if category.startswith("C"):
                    continue

                tag = char
                if char.strip() != "":
                    tag = soup.new_tag("span", attrs={"class": "ocr-char"})
                    tag.string = unicodedata.normalize("NFKC", char)

                tags.append(tag)

            elem.replace_with(*tags)
            return None

        if isinstance(elem, element.Tag) and elem.name == "svg":
            return None

        children = list(elem.children)

        for child in children:
            _add_boxes(soup, child)

    soup = BeautifulSoup(html, "html.parser")
    _add_boxes(soup, soup.body)
    html = str(soup)
    return html


def add_style(driver, style):
    script = """
        document.head.insertAdjacentHTML('beforeend', `<style>${arguments[0]}</style>`)
    """
    driver.execute_script(script, style)


def add_inline_style(driver, selector, key, value, important=False):
    priority = "important" if important else ""
    script = """
        const elems = document.querySelectorAll(arguments[0]);
        for (const elem of elems)
            elem.style.setProperty(arguments[1], arguments[2], arguments[3]);
    """
    driver.execute_script(script, selector, key, value, priority)


def update_invisible_element_priority(driver):
    add_inline_style(
        driver,
        "*[style*='display: none'], *[style*='display:none']",
        "display",
        "none",
        True,
    )
    add_inline_style(
        driver,
        "*[style*='visibility: hidden'], *[style*='visibility:hidden']",
        "visibility",
        "hidden",
        True,
    )
    add_inline_style(
        driver,
        "*[style*='visibility: collapse'], *[style*='visibility:collapse']",
        "visibility",
        "collapse",
        True,
    )
    add_inline_style(
        driver,
        "*[style*='opacity: 0'], *[style*='opacity:0']",
        "opacity",
        "0",
        True,
    )


def remove_element(driver, selector):
    script = """
        const elems = document.querySelectorAll(arguments[0]);
        for (const elem of elems)
            elem.remove();
    """
    driver.execute_script(script, selector)


def change_paragraph_fonts(driver, js_font_paths):
    script = """
        const baseFontPath = arguments[0];
        const fontPaths = arguments[1];

        const targetNodeNames = ["SECTION", "TABLE", "P", "TBODY", "H1", "H2", "H3"];
        const targetElements = Array();

        function element_list(el) {
            if (targetNodeNames.includes(el.nodeName) || el.className === "div-col") {
                targetElements.push(el);
            }
            for(let i = 0; i < el.children.length; i++) {
                element_list(el.children[i]);
            }
        }
        element_list(document);

        const newStyle = document.createElement('style');
        font2path = {};  // use in get_bbox()
        for (let i = 0; i < targetElements.length; i++) {
            const fontPath = fontPaths[Math.floor(Math.random() * fontPaths.length)];
            font2path[`font_${String(i)}, font_base`] = fontPath;
            newStyle.appendChild(document.createTextNode(`\
                @font-face {\
                    font-family: font_${String(i)};\
                    src: url('${fontPath}') format('truetype');\
                }\
            `));
        }
        newStyle.appendChild(document.createTextNode(`\
            @font-face {\
                font-family: font_base;\
                src: url('${baseFontPath}') format('truetype');\
            }\
        `));
        document.head.appendChild(newStyle);

        document.body.style.setProperty('font-family', `font_0`, 'important');
        for (let i = 0; i < targetElements.length; i++) {
            targetElements[i].style.setProperty('font-family', `font_${String(i)}, font_base`, 'important');
        }
        
        return font2path
    """
    base_font_js_path = "file:///" + str(base_font_path)
    font2path = driver.execute_script(script, base_font_js_path, js_font_paths)
    return font2path


def remove_border_bottom(driver):
    style = """
        h1, h2, h3 {
            border-bottom: none !important;
        }
    """
    add_style(driver, style)


def remove_pseudo_element(driver):
    # https://developer.mozilla.org/en-US/docs/Web/CSS/Pseudo-elements
    style = """
        *::before, *::after, ol *::marker {
            content: none !important;
        }
        *::placeholder {
            opacity: 0 !important;
        }
    """
    add_style(driver, style)


def remove_background_image(driver):
    style = """
        * {
            background-image: none !important;
        }
    """
    add_style(driver, style)


def remove_position(driver):
    style = """
        * {
            position: static !important;
        }
    """
    add_style(driver, style)


def remove_float(driver):
    style = """
        * {
            float: none !important;
        }
    """
    add_style(driver, style)


def remove_flexbox(driver):
    # https://flexboxfroggy.com/
    style = """
        * {
            flex-flow: row wrap !important;
            order: 0 !important;
        }
    """
    add_style(driver, style)


def get_boxes(driver):
    script = """
        let para_counter = 0;
        let table_counter = 0;
        const paraNodeNames = ["TH", "TR", "TD", "SECTION", "P", "H1", "H2", "H3", "DIV", "UL", "OL"];
        
        function getBoxes(node, group) {
            let boxes = [];
            const children = node.childNodes;
            const tag = node.tagName.toLowerCase();
            const text = node.innerText !== undefined ? node.innerText : '';
            const alt = node.alt !== undefined ? node.alt : '';
            const rect = node.getBoundingClientRect();
            const left = rect.left + window.scrollX;
            const top = rect.top + window.scrollY;
            const right = rect.right + window.scrollX;
            const bottom = rect.bottom + window.scrollY;
            const ratio = window.devicePixelRatio;
            const style = window.getComputedStyle(node);

            if (left < 0 || top < 0 || right < 0 || bottom < 0)
                return boxes;
            if (style.display === 'none' || style.visibility === 'hidden' || style.visibility === 'collapse' || style.opacity === '0')
                return boxes;

            if (paraNodeNames.includes(node.nodeName)) {
                group = `paragraph_${para_counter}`;
                para_counter += 1;
            }
             
            for (const child of children) {
                if (child instanceof Element) {
                    const child_rect = child.getBoundingClientRect();
                    boxes = boxes.concat(getBoxes(child, group));
                }
            }

            let box_type = null;
            
            if (tag === 'img' && node.classList.contains('mwe-math-fallback-image-inline'))
                box_type = 'latex';
            else if (tag === 'img' || tag === 'canvas' || tag === 'svg' || tag === 'video' || style.backgroundImage !== 'none')
                box_type = 'image';
            else if (tag === 'span' && node.classList.contains('ocr-char'))
                box_type = 'char';
            else if (node.nodeName === "TBODY" && node.parentNode.getAttribute('role') !== 'presentation')
                box_type = 'table'
                
            if (box_type !== null)
                boxes.push({
                    "box_type": box_type,
                    "text": text,
                    "alt": alt,
                    "bbox": [
                        Math.round(left * ratio),
                        top * ratio,
                        Math.round(right * ratio),
                        bottom * ratio,
                    ],
                    "font_family": style.getPropertyValue('font-family'),
                    "group": group
                });

            return boxes;
        }
        return getBoxes(document.body, "");
    """
    boxes = driver.execute_script(script)
    return boxes


def create_annotation(image, boxes, font2path, shrink_heuristic, lang):
    shrink_height(image, boxes, font2path, shrink_heuristic)
    make_para_polys(boxes)

    nested_annots = {
        "paragraphs": [],
        "lines": [],
        "images": [],
        "tables": [],
    }
    cl_boxes = []
    for box in boxes:
        if box["box_type"] in ["char", "latex"]:
            cl_boxes.append(box)
        elif box["box_type"] == "image":
            nested_annots["images"].append({"bbox": box["bbox"]})
        elif box["box_type"] == "table":
            nested_annots["tables"].append({"bbox": box["bbox"]})
        elif box["box_type"] == "paragraph":
            nested_annots["paragraphs"].append({"poly": box["poly"]})

    intermediate_lines = line_grouping(cl_boxes)
    lines = word_grouping(intermediate_lines, lang)
    final_line_structuring(nested_annots, lines)

    return nested_annots


def shrink_height(image, boxes, font2path, shrink_heuristic):
    if shrink_heuristic:
        buffer = np.frombuffer(image, dtype=np.uint8)
        gray = cv2.imdecode(buffer, cv2.IMREAD_GRAYSCALE)
    else:
        gray = None

    for box in boxes:
        if box["box_type"] == "char":
            font_family = box["font_family"]

            text = box["text"]
            if font_family in font2path:
                font_path = font2path[font_family][8:]
            else:
                font_path = None

            top_ratio, bottom_ratio = get_glyph_ratio(font_path, text)
            if (
                top_ratio is not None
                and bottom_ratio is not None
                and top_ratio == bottom_ratio
            ):
                top_ratio, bottom_ratio = get_glyph_ratio(str(base_font_path), text)

            if (
                top_ratio is not None
                and bottom_ratio is not None
                and top_ratio != bottom_ratio
            ):
                bbox = deepcopy(box["bbox"])
                height = bbox[3] - bbox[1]
                box["bbox"][1] = math.floor(bbox[1] + height * top_ratio)
                box["bbox"][3] = math.ceil(bbox[1] + height * bottom_ratio)
                if (
                    len(re.findall(r"[\u4e00-\u9fff]+", text)) == 1  # chinese
                    or text in "，！？；：（ ）［］【】。"  # full width chars
                ):
                    center = (box["bbox"][3] + box["bbox"][1]) // 2
                    width = box["bbox"][2] - box["bbox"][0] + 3
                    box["bbox"][1] = center - width // 2
                    box["bbox"][3] = center + width // 2

            else:
                box["bbox"][1] = math.floor(box["bbox"][1])
                box["bbox"][3] = math.ceil(box["bbox"][3])

            if shrink_heuristic:
                quad = bbox2quad(box["bbox"])
                quad = shrinkbox(gray, quad, use_otsu=False, step_size=1, threshold=10)
                box["bbox"] = quad2bbox(quad)

        elif box["box_type"] != "paragraph":
            box["bbox"][1] = math.floor(box["bbox"][1])
            box["bbox"][3] = math.ceil(box["bbox"][3])


def get_glyph_ratio(font_path, char):
    if font_path is None:
        return None, None

    try:
        if not freetype.was_init():
            freetype.init()

        font = freetype.Font(font_path)
        font.size = 100
        font.pad = False
        left, top, width, height = font.get_rect(char)
        font.pad = True
        left_pad, top_pad, width_pad, height_pad = font.get_rect(char)

        top_ratio = round((top_pad - top) / height_pad, 3)
        bottom_ratio = round((top_pad + height - top) / height_pad, 3)
        # left_ratio = round(((width_pad - width) / 2) / width_pad, 3)
        # right_ratio = round((width + (width_pad - width) / 2) / width_pad, 3)

    except:
        top_ratio = None
        bottom_ratio = None

    return top_ratio, bottom_ratio


def make_para_polys(boxes):
    group2cboxes = defaultdict(list)
    for box in boxes:
        if box["box_type"] == "char" and box["group"].startswith("paragraph_"):
            group2cboxes[box["group"]].append(box)

    for cboxes in group2cboxes.values():
        polys = [Polygon(bbox2quad(box["bbox"])) for box in cboxes]
        buf_size = math.sqrt(sum(poly.area for poly in polys) / len(polys))
        buf_size = round(buf_size * 1.5, 2)
        multi_poly = MultiPolygon(polys)

        # morphological closing
        multi_poly = multi_poly.buffer(buf_size).buffer(-buf_size)
        union = unary_union(multi_poly)

        if isinstance(union, Polygon):
            para_box = {"box_type": "paragraph", "poly": []}
            for x, y in reversed(list(union.exterior.coords)[:-1]):
                para_box["poly"].append(int(round(x)))
                para_box["poly"].append(int(round(y)))
            boxes.append(para_box)
        else:
            for geom in union.geoms:
                para_box = {"box_type": "paragraph", "poly": []}
                for x, y in reversed(list(geom.exterior.coords)[:-1]):
                    para_box["poly"].append(int(round(x)))
                    para_box["poly"].append(int(round(y)))
                boxes.append(para_box)


def line_grouping(cl_boxes):
    stretched_prev_cl_coord: Optional[List] = None
    intermediate_lines = []
    line = []
    for cl_box in cl_boxes:  # char boxes
        stretched_coord = stretch_box(cl_box["bbox"])
        if stretched_prev_cl_coord is None or (
            stretched_prev_cl_coord is not None
            and is_intersect(stretched_prev_cl_coord, stretched_coord)
        ):
            line.append(cl_box)
        else:
            intermediate_lines.append(copy.deepcopy(line))
            line = [cl_box]
        stretched_prev_cl_coord = stretched_coord

    if len(line) > 0:
        intermediate_lines.append(copy.deepcopy(line))
    return intermediate_lines


def word_grouping(intermediate_lines, lang):
    stretched_prev_cl_coord = None
    prev_type = None
    prev_text = None
    lines = []
    for inter_line in intermediate_lines:
        word = []
        line = []
        for cl_box in inter_line:
            stretched_coord = stretch_box(cl_box["bbox"], ratio=0.01)
            if stretched_prev_cl_coord is None or (
                stretched_prev_cl_coord is not None
                and is_intersect(stretched_prev_cl_coord, stretched_coord)
                and prev_type != "latex"
                and cl_box["box_type"] != "latex"
                and prev_text not in "。｡「」『』、"
            ):
                if lang == "zh" and prev_text is not None:
                    if prev_text not in "!:.,?，！？；：":
                        word.append(copy.deepcopy(cl_box))
                    else:
                        line.append(copy.deepcopy(word))
                        word = [cl_box]
                else:
                    word.append(copy.deepcopy(cl_box))
            else:
                line.append(copy.deepcopy(word))
                word = [cl_box]
            stretched_prev_cl_coord = stretched_coord
            prev_type = cl_box["box_type"]
            prev_text = cl_box["text"]

        if len(word) > 0:
            line.append(copy.deepcopy(word))
            stretched_prev_cl_coord = None

        lines.append(copy.deepcopy(line))
    return lines


def final_line_structuring(nested_annots, lines):
    for line in lines:
        line_dict = {"words": [], "bbox": []}
        for word in line:
            word_dict = {
                "is_latex": False,
                "chars": [],
                "text": "",
                "bbox": [],
            }
            for char in word:
                if char["box_type"] == "latex":
                    assert len(word) == 1
                    word_dict = {
                        "is_latex": True,
                        "chars": None,
                        "text": char["alt"].replace("\\\\displaystyle ", ""),
                        "bbox": char["bbox"],
                    }
                else:
                    char_dict = {
                        "bbox": char["bbox"],
                        "text": char["text"],
                    }
                    word_dict["chars"].append(char_dict)

            if word_dict["chars"] is not None:
                word_dict["text"] = "".join(
                    char_dict["text"] for char_dict in word_dict["chars"]
                )
                word_dict["bbox"] = get_enclosing_bbox(
                    [char_dict["bbox"] for char_dict in word_dict["chars"]]
                )

            line_dict["words"].append(word_dict)
        line_dict["bbox"] = get_enclosing_bbox(
            [word["bbox"] for word in line_dict["words"]]
        )
        nested_annots["lines"].append(line_dict)


def get_version_str(target_lang, num_train, chunk_idx):
    current_time = time.strftime("%Y_%m_%d", time.localtime(time.time()))
    num_train = human_format(num_train)
    ver_str = f"{target_lang}_{current_time}_{num_train}"
    if chunk_idx is not None:
        ver_str += f"_{chunk_idx}"
    return ver_str


def human_format(num):
    magnitude = 0
    while abs(num) >= 1000:
        magnitude += 1
        num /= 1000.0
    return "%d%s" % (round(num), ["", "K", "M", "G", "T", "P"][magnitude])


def get_enclosing_bbox(bbox_coords_list):
    x1 = 9999999
    y1 = 9999999
    x2 = -1
    y2 = -1
    for bbox_coords in bbox_coords_list:
        if bbox_coords[0] < x1:
            x1 = bbox_coords[0]
        if bbox_coords[1] < y1:
            y1 = bbox_coords[1]
        if bbox_coords[2] > x2:
            x2 = bbox_coords[2]
        if bbox_coords[3] > y2:
            y2 = bbox_coords[3]

    return [x1, y1, x2, y2]


def is_intersect(bbox_coords1: List, bbox_coords2: List) -> bool:
    # obtain x1, y1, x2, y2 of the intersection
    x1 = max(bbox_coords1[0], bbox_coords2[0])
    y1 = max(bbox_coords1[1], bbox_coords2[1])
    x2 = min(bbox_coords1[2], bbox_coords2[2])
    y2 = min(bbox_coords1[3], bbox_coords2[3])

    w = x2 - x1
    h = y2 - y1
    return w >= 0 and h >= 0


def stretch_box(bbox_coords: List, ratio: float = 1.0) -> List:
    """x 방향으로 box y 크기만큼 bbox_coords 를 늘려줌"""
    height = bbox_coords[3] - bbox_coords[1]
    new_coords = copy.deepcopy(bbox_coords)
    new_coords[0] -= max(height * ratio, 1)
    new_coords[2] += max(height * ratio, 1)
    return new_coords


def bbox2quad(bbox):
    """x1y1x2y2 to quad"""
    quad = np.array(
        [
            [bbox[0], bbox[1]],
            [bbox[2], bbox[1]],
            [bbox[2], bbox[3]],
            [bbox[0], bbox[3]],
        ],
        dtype=np.int32,
    )
    return quad


def quad2bbox(quad):
    """quad to x1y1x2y2"""
    bbox = [
        int(round(quad[0, 0])),
        int(round(quad[0, 1])),
        int(round(quad[2, 0])),
        int(round(quad[2, 1])),
    ]
    return bbox


if __name__ == "__main__":
    fire.Fire(main)
