import sys
from os.path import abspath, dirname

sys.path.append(dirname(dirname(abspath(__file__))))

from webvicob.wikipedia.wikipedia import main


def test_basic():
    main(
        workspace="./resources/workspace_example",
        target_lang="en",
        num_train=10,
        num_val=1,
        num_test=1,
        debug=True,
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
        chrome_path="resources/chromedriver",
        html_section_chunker=True,
    )
