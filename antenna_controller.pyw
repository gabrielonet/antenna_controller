import tkinter as tk
from tkinter import ttk
import serial
import socket
import re
import multiprocessing
from multiprocessing import Process, Value, Manager
import serial.tools.list_ports
import os
import ctypes
import time 

# Setup directories and config
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "decoder_config.txt")

def save_config(port_name):
    try:
        clean_name = port_name.split(" ")[0]
        with open(CONFIG_FILE, "w") as f:
            f.write(clean_name)
            f.flush()
            os.fsync(f.fileno()) 
    except Exception as e:
        print(f"Error saving config: {e}")

def load_config():
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                return f.read().strip()
    except Exception:
        pass
    return "COM15"

# --- GUI Initialization ---
root = tk.Tk()
root.title("Antenna controller by yo8rxp, v1.01")
root.geometry("460x380") 
root.resizable(False, False)

try:
    myappid = 'yo8rxp.antenna.controller.3.0'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except Exception:
    pass

frame = tk.Frame(root)
frame.pack(padx=10, pady=10)

ant_buttons = []
aux_buttons = []

# Separate mappings for independent tracking[cite: 2]
ant_map = {160: 0, 80: 1, 40: 2, 20: 3, 15: 4, 10: 5}
aux_map = {201: 0, 202: 1, 203: 2, 204: 3, 205: 4, 206: 5}

def butoane(band_value):
    serial_data.value = band_value

ant_labels = ["Ant 1", "Ant 2", "Ant 3", "Ant 4", "Ant 5", "Ant 6"]
ant_values = [160, 80, 40, 20, 15, 10]

aux_labels = ["Aux 1", "Aux 2", "Aux 3", "Aux 4", "Aux 5", "Aux 6"]
aux_values = [201, 202, 203, 204, 205, 206]

# Ant Buttons: Rows 0 and 1[cite: 2]
for i in range(6):
    r = i // 3
    c = i % 3
    btn = tk.Button(frame, text=ant_labels[i], bg="grey", fg="white", 
                    width=10, height=2, command=lambda v=ant_values[i]: butoane(v))
    btn.grid(row=r, column=c*2, columnspan=2, padx=3, pady=5)
    ant_buttons.append(btn)

# ALL OFF Button: Row 2[cite: 2]
all_off_btn = tk.Button(frame, text="ALL OFF", bg="darkred", fg="white", font=("Arial", 9, "bold"),
                        width=12, height=1, command=lambda: butoane(0))
all_off_btn.grid(row=2, column=2, columnspan=2, pady=10)

# Horizontal Line (Separator)[cite: 2]
separator = ttk.Separator(frame, orient='horizontal')
separator.grid(row=3, column=0, columnspan=6, sticky="ew", pady=10)

# Aux Buttons: Row 4[cite: 2]
for i in range(6):
    btn = tk.Button(frame, text=aux_labels[i], bg="grey", fg="white", 
                    width=8, height=2, command=lambda v=aux_values[i]: butoane(v))
    btn.grid(row=4, column=i, padx=2, pady=5)
    aux_buttons.append(btn)

p2 = None 

def start_serial():
    global p2
    selected_port = port_var.get()
    status_label.config(text="Connecting...", fg="blue")
    root.update_idletasks()
    
    if "(Not Available)" in selected_port:
        status_label.config(text="COM Port Busy!", fg="red")
        return

    if p2 and p2.is_alive():
        running_flag.value = False
        p2.join(timeout=0.5)
        p2.terminate()
    
    running_flag.value = True
    save_config(selected_port)
    p2 = multiprocessing.Process(target=serial_port, args=(selected_port, serial_data, running_flag, udp_data))
    p2.start()
    status_label.config(text="Connected", fg="green")

bottom_frame = tk.LabelFrame(root, text="Settings")
bottom_frame.pack(side="bottom", fill="x", padx=10, pady=10)

port_var = tk.StringVar()
port_menu = ttk.Combobox(bottom_frame, textvariable=port_var, width=18, state="readonly")
port_menu.grid(row=0, column=1, padx=5, pady=5)

def refresh_ports():
    system_ports = [port.device for port in serial.tools.list_ports.comports()]
    saved_port = load_config()
    display_list = system_ports if saved_port in system_ports else system_ports + [f"{saved_port} (Not Available)"]
    port_menu['values'] = sorted(display_list)
    port_var.set(saved_port if saved_port in system_ports else f"{saved_port} (Not Available)")

refresh_ports()
tk.Button(bottom_frame, text="↻", command=refresh_ports, width=2).grid(row=0, column=2, padx=2)
tk.Button(bottom_frame, text="Apply", command=start_serial).grid(row=0, column=3, padx=5, pady=5)
status_label = tk.Label(bottom_frame, text="", font=("Arial", 8, "bold"))
status_label.grid(row=1, column=0, columnspan=4, pady=5)

# --- UDP SERVER ---
def udp_server(udp_data, serial_data):
    UDPServerSocket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
    UDPServerSocket.bind(("127.0.0.1", 12000))
    UDPServerSocket.settimeout(0.5) 
    freq_temp = 0
    while True:
        try:
            data, _ = UDPServerSocket.recvfrom(1024)
            message = data.decode('utf-8')
            match = re.search(r"<Freq>(\d+)", message)
            if match:
                freq = int(match.group(1))
                if freq != freq_temp:
                    freq_temp = freq
                    for b, (low, high) in {160:(100,300), 80:(320,500), 40:(500,800), 20:(1300,1500), 15:(2000,2300), 10:(2700,3000)}.items():
                        if low*1000 <= freq <= high*1000:
                            udp_data.value = b
                            serial_data.value = b
                            break
            time.sleep(0.01)
        except: continue

# --- SERIAL PROCESS ---
def serial_port(selected_port, serial_data, running_flag, udp_data):
    clean_port = selected_port.split(" ")[0]
    end_string = b'\xFF\xFF\xFF'
    last_poll_time = 0
    poll_interval = 0.25 
    
    try:
        ser = serial.Serial(clean_port, 9600, timeout=0.01) 
        ser.reset_input_buffer()
        
        while running_flag.value:
            current_now = time.time()
            if current_now - last_poll_time > poll_interval:
                ser.write("get rx.val".encode() + end_string)
                ser.write("get aux.val".encode() + end_string)
                last_poll_time = current_now

            if serial_data.value != -1:
                val = serial_data.value
                if 201 <= val <= 206:
                    ser.write(f"aux.val={val}".encode() + end_string)
                    ser.write("execute_aux.en=1".encode() + end_string)
                elif val == 0: 
                    ser.write(b"rx.val=107" + end_string)
                    ser.write(b"execute_rx.en=1" + end_string)
                    udp_data.value = 0 
                else:
                    nx_map = {160:101, 80:102, 40:103, 20:104, 15:105, 10:106}
                    nx_val = nx_map.get(val, 0)
                    if nx_val:
                        ser.write(f"rx.val={nx_val}".encode() + end_string)
                        ser.write("execute_rx.en=1".encode() + end_string)
                serial_data.value = -1 

            if ser.in_waiting:
                data = ser.read(ser.in_waiting)
                if b'\x71' in data:
                    idx = data.find(b'\x71')
                    if len(data) >= idx + 5:
                        num = int.from_bytes(data[idx+1:idx+5], 'little')
                        mapping = {
                            101:160, 102:80, 103:40, 104:20, 105:15, 106:10,
                            107:0,
                            201:201, 202:202, 203:203, 204:204, 205:205, 206:206
                        }
                        if num in mapping: 
                            udp_data.value = mapping[num]

                try:
                    decoded = data.decode('utf-8', errors='ignore')
                    match = re.search(r"(10[1-7]|20[1-6])", decoded)
                    if match:
                        found = match.group()
                        mapping = {
                            "101":160, "102":80, "103":40, "104":20, "105":15, "106":10,
                            "107":0,
                            "201":201, "202":202, "203":203, "204":204, "205":205, "206":206
                        }
                        udp_data.value = mapping[found]
                except: pass

            time.sleep(0.01)
    except: pass
    finally:
        if 'ser' in locals(): ser.close()

# --- GUI UPDATE ---
# Fix: Initialize these variables in the global scope[cite: 2]
last_ant_val = -1 
last_aux_val = -1 

def update_gui():
    global last_ant_val, last_aux_val
    current_val = udp_data.value
    
    # Check for "All Off" (0)[cite: 2]
    if current_val == 0:
        if last_ant_val != 0:
            for btn in ant_buttons: 
                btn.config(bg="grey")
            all_off_btn.config(bg="red") # Turn bright red when active[cite: 2]
            last_ant_val = 0
    
    # Update Ant Buttons[cite: 2]
    elif current_val in ant_map and current_val != last_ant_val:
        last_ant_val = current_val
        all_off_btn.config(bg="darkred") # Revert to default color[cite: 2]
        for btn in ant_buttons: 
            btn.config(bg="grey")
        ant_buttons[ant_map[current_val]].config(bg="red")
        
    # Update Aux Buttons[cite: 2]
    elif current_val in aux_map and current_val != last_aux_val:
        last_aux_val = current_val
        for btn in aux_buttons: 
            btn.config(bg="grey")
        aux_buttons[aux_map[current_val]].config(bg="red")
        
    root.after(50, update_gui)

def on_closing():
    running_flag.value = False
    if p2: p2.terminate()
    root.destroy()

if __name__ == "__main__":
    manager = Manager()
    running_flag = manager.Value('b', True)
    udp_data = manager.Value('i', 0)
    serial_data = manager.Value('i', -1) 
    
    multiprocessing.Process(target=udp_server, args=(udp_data, serial_data), daemon=True).start()
    
    start_serial()
    root.protocol("WM_DELETE_WINDOW", on_closing)
    update_gui()
    root.mainloop()