import cv2
import numpy as np

def find_puzzle_gap(bg_bytes: bytes, piece_bytes: bytes = None) -> float:
    # Decode background
    bg_arr = np.frombuffer(bg_bytes, np.uint8)
    bg_img = cv2.imdecode(bg_arr, cv2.IMREAD_COLOR)
    
    if piece_bytes:
        piece_arr = np.frombuffer(piece_bytes, np.uint8)
        piece_img = cv2.imdecode(piece_arr, cv2.IMREAD_UNCHANGED)
        
        # If piece has alpha channel
        if piece_img.shape[2] == 4:
            alpha = piece_img[:, :, 3]
            template = cv2.cvtColor(piece_img, cv2.COLOR_BGRA2BGR)
            # Edge match
            bg_gray = cv2.cvtColor(bg_img, cv2.COLOR_BGR2GRAY)
            piece_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
            
            bg_edge = cv2.Canny(bg_gray, 100, 200)
            piece_edge = cv2.Canny(piece_gray, 100, 200)
            
            res = cv2.matchTemplate(bg_edge, piece_edge, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
            return float(max_loc[0])
    
    # Fallback Canny gap finder on background alone (find the missing notch)
    bg_gray = cv2.cvtColor(bg_img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(bg_gray, 100, 200)
    # Mask out left 40px (where piece starts)
    edges[:, :50] = 0
    # Find contours
    contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if 35 <= w <= 65 and 35 <= h <= 65:
            return float(x)
            
    return 200.0
