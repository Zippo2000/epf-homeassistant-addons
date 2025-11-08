# cython: language_level=3
# cython: boundscheck=False, wraparound=False, nonecheck=False

import numpy as np
cimport numpy as np
cimport cython
from libc.math cimport pow
from PIL import Image
from libc.stdint cimport uint16_t, uint32_t

# Constants
EPD_W = 800
EPD_H = 480

ctypedef np.float32_t FLOAT_TYPE
ctypedef np.uint8_t UINT8_TYPE

cdef uint32_t sqDiff(uint16_t a, uint16_t b) nogil:
    return (a - b) * (a - b)

#---------------------
# Original Floyd-Steinberg
cdef int closestColor(uint16_t r, uint16_t g, uint16_t b, double[:, :] linearPalette) nogil:
    """
    找出最接近的顏色索引，使用加權的平方距離計算
    """
    cdef int color = 0
    cdef uint32_t best = 2**32 - 1  # MaxUint32
    cdef uint32_t dist
    cdef int i, j
    cdef double rr, gg, bb
    
    for i in range(linearPalette.shape[0]):
        rr = linearPalette[i, 0]
        gg = linearPalette[i, 1]
        bb = linearPalette[i, 2]
        
        # 使用加權的平方距離計算
        dist = (
            ((1063 * sqDiff(r, <uint16_t>(rr * 255)) // 5000)) +
            ((447 * sqDiff(g, <uint16_t>(gg * 255)) // 625)) +
            ((361 * sqDiff(b, <uint16_t>(bb * 255)) // 5000))
        )
        
        if dist < best:
            if dist == 0:
                return i
            color = i
            best = dist
    
    return color

cdef double gamma_linear(double inp) nogil:
    if inp > 0.04045:
        return pow((inp + 0.055) / (1.0 + 0.055), 2.4)
    return inp / 12.92

def load_scaled(image, angle, display_mode='fit'):
    if isinstance(image, str):
        img = Image.open(image)
    else:
        img = image.copy()
    
    img = img.convert('RGB')
    img = img.rotate(angle, expand=True)
    
    if display_mode == 'fill':
        orig_ratio = img.width / img.height
        epd_ratio = EPD_W / EPD_H
        
        if orig_ratio > epd_ratio:
            new_height = EPD_H
            new_width = int(new_height * orig_ratio)
            img = img.resize((new_width, new_height), Image.LANCZOS)
            left = (new_width - EPD_W) // 2
            img = img.crop((left, 0, left + EPD_W, EPD_H))
        else:
            new_width = EPD_W
            new_height = int(new_width / orig_ratio)
            img = img.resize((new_width, new_height), Image.LANCZOS)
            top = (new_height - EPD_H) // 2
            img = img.crop((0, top, EPD_W, top + EPD_H))
    else:
        orig_ratio = img.width / img.height
        epd_ratio = EPD_W / EPD_H
        
        if orig_ratio > epd_ratio:
            new_width = EPD_W
            new_height = int(new_width / orig_ratio)
        else:
            new_height = EPD_H
            new_width = int(new_height * orig_ratio)
        
        img = img.resize((new_width, new_height), Image.LANCZOS)
        bg = Image.new('RGB', (EPD_W, EPD_H), (255, 255, 255))
        offset = ((EPD_W - new_width) // 2, (EPD_H - new_height) // 2)
        bg.paste(img, offset)
        return bg
    
    return img

def convert_image(input_image, preview_path=None, dithering_strength=1.0):
    """Cython-optimized image conversion with Floyd-Steinberg dithering."""
    cdef np.ndarray[np.uint8_t, ndim=3] img_array = np.array(input_image, dtype=np.uint8)
    
    # KORRIGIERTE PALETTE - Waveshare Spectra 6
    cdef double[:, :] epd_colors = np.array([
        [0.0, 0.0, 0.0],          # Black
        [1.0, 1.0, 1.0],          # White
        [1.0, 0.953, 0.220],      # Yellow (255, 243, 56)
        [0.749, 0.0, 0.0],        # Red (191, 0, 0)
        [0.392, 0.251, 1.0],      # Blue (100, 64, 255)
        [0.263, 0.541, 0.110]     # Green (67, 138, 28)
    ], dtype=np.float64)
    
    cdef np.ndarray[np.uint8_t, ndim=3] pixels = np.zeros((EPD_H, EPD_W, 3), dtype=
