"""
WEBVICOB
Copyright 2022-present NAVER Corp.
Apache-2.0
"""
import cv2
import numpy as np


def shrinkbox(gray, quad, use_otsu=False, threshold=50.0, step_size=1):
    """Perform shrink_box
    Args:
        gray: grayscaled image
        quad: quadrangle (4, 2)
        use_otsu (bool): OTSU threshold를 사용할 지 말지.
        threshold (float): shrink-box threshold
    Returns:
        quad: shrinked quadrangle (4, 2)
    """
    h, w = gray.shape

    # 이미지 boundary 를 넘어가면 작동 x
    xmax, ymax = np.max(quad, axis=0)
    if np.min(quad) < 0 or xmax >= w or ymax >= h:
        return quad

    if use_otsu:
        xmin, ymin = np.min(quad, axis=0)
        bin_gray = np.zeros((h, w), dtype=np.uint8)
        gray[ymin:ymax, xmin:xmax] = cv2.GaussianBlur(gray[ymin:ymax, xmin:xmax], (5, 5), 0)
        threshold, bin_patch = cv2.threshold(gray[ymin:ymax, xmin:xmax], 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        bin_gray[ymin:ymax, xmin:xmax] = bin_patch
    else:
        bin_gray = gray

    center = np.mean(quad, axis=0)

    for i, point in enumerate(quad):
        if i in [1, 3]:  # 세로만 줄임
            continue

        aaa, bbb = point, quad[(i + 1) % len(quad)]
        unitvec = _unitlinenormal(bbb, aaa) * step_size

        points_val = _get_points_value(bin_gray, _linspace2d(aaa, bbb, w, h))
        if len(points_val) == 0:
            continue
        max_step = int(_distance((aaa + bbb) / 2, center) / 2)

        meanval = sum(points_val) / len(points_val)
        minval = min(points_val)
        maxval = max(points_val)

        if _checkcontinue(meanval, minval, maxval, threshold):
            for _ in range(max_step):
                points_val = _get_points_value(bin_gray, _linspace2d(aaa, bbb, w, h))
                minval, maxval = min(points_val), max(points_val)
                if not _checkcontinue(meanval, minval, maxval, threshold):
                    aaa = aaa - unitvec
                    bbb = bbb - unitvec
                    break
                aaa = aaa + unitvec
                bbb = bbb + unitvec

        quad[i] = aaa
        quad[(i + 1) % len(quad)] = bbb

    return quad


def _linspace2d(point1, point2, imgw, imgh):
    """두 2D 점 사이의 등간격 점 좌표들을 반환
    sampling 수는 point1과 point2의 거리로 계산
    """
    n_sample_points = int(np.linalg.norm(point1 - point2))
    v1 = np.linspace(point1[0], point2[0], n_sample_points)
    v2 = np.linspace(point1[1], point2[1], n_sample_points)
    line = np.zeros(shape=[n_sample_points, 2])
    line[:, 0] = np.clip(v1, 0, imgw - 1)
    line[:, 1] = np.clip(v2, 0, imgh - 1)
    return np.round_(line).astype(np.int64)


def _get_points_value(npimg, linepoints):
    """Return list of values of cordinates in linepoints"""
    return [npimg[y][x] for x, y in linepoints]


def _unitlinenormal(pnt1, pnt2):
    """Apply -90deg rotation of vec(pnt1, pnt2) and normalize
    Args:
        pnt1 (NDArray[float32]): 시계방향 기준 pnt2 다음 point (1, 2)
        pnt2 (NDArray[float32]): 시계방향 기준 pnt1 이전 point (1, 2)
    """
    normalvec = (pnt2 - pnt1)[::-1] * np.array([1, -1])
    return normalvec / (np.linalg.norm(normalvec) + 1e-6)


def _checkcontinue(mean, minval, maxval, threshold):
    """계속해서 박스를 줄여 나갈지 말 지 결정"""
    return 0 <= maxval - mean < threshold and 0 <= mean - minval < threshold


def _distance(pnt1, pnt2):
    """l2 distance"""
    return np.sqrt(np.sum((pnt1 - pnt2) ** 2))
