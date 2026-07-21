import network
import sys
import time

import envoy_auth
from ili9341 import Display, color565
from machine import Pin, SPI  # type: ignore
from xglcd_font import XglcdFont
from secrets import WIFI_SSID, WIFI_PASSWORD

MAX_HISTORY = 64
GRAPH_Y = 82        # top of graph area (3 text lines * 26px + 4px gap)
GRAPH_H = 158       # height of graph area (240 - GRAPH_Y - 2)
GRAPH_W = 320       # full display width

def draw_graph(display, gen_history, use_history):
    green_color = color565(0, 200, 0)
    red_color   = color565(220, 50, 50)
    bg_color    = color565(15, 15, 15)
    white_color = color565(255, 255, 255)
    dim_color   = color565(45, 45, 45)

    display.fill_rectangle(0, GRAPH_Y, GRAPH_W, GRAPH_H, bg_color)

    n = len(gen_history)
    if n < 2:
        return

    all_vals = gen_history + use_history
    max_val = max(all_vals)
    if max_val <= 0:
        max_val = 1

    y_bottom = GRAPH_Y + GRAPH_H - 1
    y_mid    = GRAPH_Y + GRAPH_H // 2
    y_top    = GRAPH_Y

    # Grid lines at 50% and 100%
    display.draw_hline(0, y_mid, GRAPH_W, dim_color)

    # Scale labels (8x8 built-in font): max at top, mid, 0 at bottom
    display.draw_text8x8(2, y_top + 1,   f"{thousands(int(max_val))}W", white_color, bg_color)
    display.draw_text8x8(2, y_mid - 4,   f"{thousands(int(max_val // 2))}W", white_color, bg_color)
    display.draw_text8x8(2, y_bottom - 8, "0W", white_color, bg_color)

    x_step = GRAPH_W / n

    def val_to_y(val):
        return y_bottom - int(max(val, 0) / max_val * (GRAPH_H - 1))

    for i in range(1, n):
        x1 = int((i - 1) * x_step)
        x2 = int(i * x_step)
        display.draw_line(x1, val_to_y(gen_history[i - 1]), x2, val_to_y(gen_history[i]), green_color)
        display.draw_line(x1, val_to_y(use_history[i - 1]), x2, val_to_y(use_history[i]), red_color)

def main():
    # Function to set up SPI for TFT display
    display_spi = SPI(1, baudrate=40000000, sck=Pin(14), mosi=Pin(13))
    # Set up display
    display = Display(display_spi, dc=Pin(2), cs=Pin(15), rst=Pin(15),
                  width=320, height=240, rotation=90)

    # Set colors
    white_color = color565(255, 255, 255)  # white color
    black_color = color565(0, 0, 0)        # black color

    # Turn on display backlight
    backlight = Pin(21, Pin.OUT)
    backlight.on()

    # Clear display
    display.clear(black_color)

    espresso_dolce = XglcdFont('fonts/EspressoDolce18x24.c', 18, 24)
    display.clear()
    display.draw_text(0, 2, f"Connecting to '{WIFI_SSID}'...", espresso_dolce, white_color)

    gen_history = []
    use_history = []

    # "Requesting..." indicator: 8x8 font, top-right corner
    req_label = "Requesting..."
    req_x = GRAPH_W - len(req_label) * 8 - 2
    req_y = GRAPH_Y - 10  # just above the graph, clear of the text lines

    while True:
        connect_wifi()
        display.draw_text8x8(req_x, req_y, req_label, white_color, black_color)
        try:
            solarData = envoy_auth.fetch_envoy_json("/production.json")
        except Exception as e:
            sys.print_exception(e)
        else:
            generating = solarData["production"][1]["wNow"]  # gives a float
            using = solarData["consumption"][0]["wNow"]
            print(f"generating {generating}W")
            print(f"using {using}W")
            net = generating - using
            genString =   f"Generating: {int(generating)}W"
            usingString = f"Using:      {int(using)}W"
            netString =   f"Net:        {int(net)}W"

            gen_history.append(generating)
            use_history.append(using)
            if len(gen_history) > MAX_HISTORY:
                gen_history = gen_history[-MAX_HISTORY:]
                use_history = use_history[-MAX_HISTORY:]

            # Clear only the text area, leave graph intact until redrawn below
            display.fill_rectangle(0, 0, GRAPH_W, GRAPH_Y, black_color)
            display.draw_text(10, 2,  genString,   espresso_dolce, white_color)
            display.draw_text(10, 28, usingString, espresso_dolce, white_color)
            display.draw_text(10, 54, netString,   espresso_dolce, white_color)
            draw_graph(display, gen_history, use_history)
        time.sleep(10)


def thousands(n):
    s = str(n)
    out = ""
    while s:
        out = ("," + s[-3:] + out) if out else s[-3:]
        s = s[:-3]
    return out

# -------- Connect to WiFi --------
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if not wlan.isconnected():
        print(f"Connecting to {WIFI_SSID}...")
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)

        timeout = 10  # seconds
        start = time.time()
        while not wlan.isconnected():
            if time.time() - start > timeout:
                raise RuntimeError("WiFi connection failed")
            time.sleep(0.5)

    print("Connected to WiFi")

if __name__ == "__main__":
    main()
