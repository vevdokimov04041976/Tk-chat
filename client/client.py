import socket
from threading import Thread, Event as ThreadEvent
from time import sleep, time
import datetime
import sys
from random import random
from tkinter import *
from tkinter import messagebox
from tkinter import scrolledtext
from tkinter import *
import json
import sqlite3
from PIL import Image, ImageTk
from functools import partial
import base64
import io
import pyaudio
from random import randint
import wave
import uuid

result_of_connect = 22
conn_number = 0
current_page = 0
current_page_local = 0
is_fetching = False
earliest_timestamp = 10e+12
CLIENT_ID = str(random())
FORMAT = pyaudio.paInt16
CHANNELS = 2
RATE = 44100
CHUNK = 1024
WAVE_OUTPUT_FILENAME = "file.wav"
frames = []
audio_rec = None
stream_rec = None
audio_out = False
audio_out_stop = False
current_audioLabel = None
playing_event = ThreadEvent()
playing_event.set()

    
username_from_db = None
db_conn = sqlite3.connect('users_log.db', check_same_thread=False)

def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

db_conn.row_factory = dict_factory

cursor = db_conn.cursor()


def init_db():
    cursor.execute('''CREATE TABLE IF NOT EXISTS username(username text, timestamp integer)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS message(username text, text text, timestamp integer)''')
    db_conn.commit()


HOST = ''    # The remote host
if len(sys.argv) > 1:
    PORT = int(sys.argv[1])
    randomly = int(sys.argv[2])
else:
    PORT = 50082
    randomly = 0

s = None 

def _connect():
    global s, result_of_connect, conn_number
    #sleep(5)
    while result_of_connect != 0:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result_of_connect = s.connect_ex((HOST, PORT + conn_number % 5))
        #print('попытка установления соединения:', result_of_connect)
        if result_of_connect == 0:
            th1 = Thread(target=receiver, args = (s, ))
            th1.start()
        else:
            #print('result_of_connect is not 0', result_of_connect)
            conn_number += 1
            s.close()
        sleep(2)

def connect():
    thread=Thread(target=_connect)
    thread.start()

def send_data(data):
    try:
        #print('SENDING MESSAGE TO SERVER!!!')
        data['client_id'] = CLIENT_ID
        s.sendall(json.dumps(data).encode('utf-8') + b'\x00')
    except (BrokenPipeError, OSError) as err:
        print('соединение закрыто сервером', err)

def send_message(name, text):
    if s is None: return
    data = {'type': 'message', 'username': name,'text': text, 'timestamp' : time()}
    #print('printing inserting','''INSERT INTO client_username_db VALUES (?)''', (data['username']))
    cursor.execute('''INSERT INTO username VALUES (?,?)''', (data['username'], data['timestamp']))
    db_conn.commit()
    send_data(data)

def get_next_msg():
    global is_fetching, earliest_timestamp
    if s is None or is_fetching: return
    data = {'type': 'last_messages', 'timestamp' : earliest_timestamp}
    is_fetching = True
    send_data(data)
    
def get_next_image(filename):
    data = {'type': 'get_image', 'filename' : filename}
    #is_fetching = True
    send_data(data)

def from_local_db():
    global earliest_timestamp, current_page_local
    cursor.execute('SELECT * FROM message WHERE timestamp < {0} ORDER BY timestamp DESC LIMIT 20;'.format(earliest_timestamp))
    messages = cursor.fetchall()
    if messages:
        if not current_page_local:
            messages.reverse()
            earliest_timestamp = messages[0]['timestamp']
        else:
            earliest_timestamp = messages[-1]['timestamp']
    #print('messages', messages)
    for msg in messages:
        username = msg['username']
        text = msg['text']
        timestamp = msg['timestamp']
        add_message(username, text, timestamp, current_page_local!=0)
        current_page_local += 1
        #print('current_page_local в локал ДБ в цикле:', current_page_local)
    print('current_page_local в локал ДБ итого:', current_page_local)
    
def receiver(s):
    global is_fetching, earliest_timestamp, current_page, result_of_connect
    data = b''
    while True:
        #print('starting receiver')
        try:
            chunk = s.recv(1024)
        except OSError as err:
            print('соединение закрыто', err)
            break
        if not chunk:
            print('NO CHUNK!!!')
            result_of_connect = 22
            break
        data += chunk
        while b'\x00' in data:
                #print('NEXT', data)
                ind = data.index(b'\x00')
                result = data[:ind].decode('utf-8')
                data = data[ind+1:]
                obj = json.loads(result)
                #print(obj['type'])
                if obj['type'] == 'message':
                    username = obj['username']
                    text = obj['text']
                    timestamp = obj['timestamp']
                    #print('printing inserting', '''INSERT INTO message VALUES (NULL, '{username}', '{text}', {timestamp})'''.format(username=obj['username'], text=obj['text'], timestamp=obj['timestamp']))
                    cursor.execute('''INSERT INTO message VALUES (?, ?, {timestamp})'''.format(timestamp=timestamp), (username, text))
                    db_conn.commit()
                    add_message(username, text, timestamp)
                elif obj['type'] == 'users':
                    amount = obj['amount']
                    change_users(amount)
                elif obj['type'] == 'last_messages':
                    print('current_page в принятых сообщениях :', current_page)
                    if not current_page:
                        print('current_page в принятых сообщениях до очистки сообщений:', current_page)
                        clear_messages()
                    if obj['messages']:
                        if obj['messages'][-1]['timestamp'] > earliest_timestamp:
                            continue
                        earliest_timestamp = obj['messages'][-1]['timestamp']
                        if not current_page:
                            obj['messages'].reverse()
                    for msg in obj['messages']:
                        username = msg['username']
                        text = msg['text']
                        timestamp = msg['timestamp']
                        #print('timestamp полученный от сервера по last_messages', timestamp)
                        #print('printing inserting', '''INSERT INTO message VALUES (NULL, '{username}', '{text}', {timestamp})'''.format(username=obj['username'], text=obj['text'], timestamp=obj['timestamp']))
                        cursor.execute('''INSERT INTO message VALUES (?, ?, {timestamp})'''.format(timestamp=timestamp), (username, text)) #добавлени посл сообщений при коннекте
                        add_message(username, text, timestamp, current_page!=0)
                    is_fetching = False
                    db_conn.commit()
                    current_page += 1
                    print('current_page при коннекте += 1:', current_page)
                elif obj['type'] == 'image':
                    if CLIENT_ID != obj['client_id']:
                        file = obj['file']
                        file = base64.b64decode(file)
                        print('принят файл типа картинка', type(file))
                        image = Image.open(io.BytesIO(file))
                        add_img_label(image)
                elif obj['type'] == 'last_images':
                    print('obj[images]', obj['images'])
                    images = obj['images']
                    for image in images:
                        filename = image['filename']
                        get_next_image(filename)
                elif obj['type'] == 'get_image':
                    file = obj['file']
                    file = base64.b64decode(file)
                    image = Image.open(io.BytesIO(file))
                    add_img_label(image)
                elif obj['type'] == 'audio':
                    if CLIENT_ID != obj['client_id'] or True:
                        username = obj['username']
                        file = obj['file']
                        file = base64.b64decode(file)
                        filename = str(uuid.uuid1())+'.wav'
                        with open(filename, 'wb') as f:
                            f.write(file)
                        add_audio_label(username, filename)
                    
    sleep(5)
    print('попытка нового connect')
    connect()                    
                    
""" with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.connect((HOST, PORT))
    th1 = Thread(target=receiver, args = (s, ))
    th1.start()
    while True:
        if not randomly:
            text = input('Enter some text :\n')
        else:
            text = 'bot sent ' + str(round(1000*random()))
        s.sendall(text.encode('utf-8')+b'abcd\x000adidas'+b'\x00')
        sleep(0.5)
"""
class EntryWithPlaceholder(Entry):
    def __init__(self, master=None, placeholder="PLACEHOLDER", color='grey', on_input=None):
    
        super().__init__(master)

        self.placeholder = placeholder
        self.placeholder_color = color
        self.default_fg_color = self['fg']

        self.bind("<FocusIn>", self.foc_in)
        self.bind("<FocusOut>", self.foc_out)
        
        if on_input:
            def handle_input(event=None):
                #print(dir(event), event.char)
                text1 = self.get()
                empty = self.is_empty()
                if empty:
                    text1 = ''
                on_input(text1)
            self.bind('<KeyRelease>', handle_input)

        self.put_placeholder()

    def put_placeholder(self):
        self.insert(0, self.placeholder)
        self['fg'] = self.placeholder_color

    def foc_in(self, *args):
        if self['fg'] == self.placeholder_color:
            self.delete('0', 'end')
            self['fg'] = self.default_fg_color

    def foc_out(self, *args):
        if not self.get():
            self.put_placeholder()
    def is_empty(self):
        return not self.get() or self['fg'] == self.placeholder_color
    def set_text(self, text):
        #print('set text', text)
        self.delete('0', 'end')
        self.insert(0, text)
        self['fg'] = self.default_fg_color

def add_message(username, text, timestamp, begin=False):
    data = username + ': ' + text + ' (' + '{0:%Y-%m-%d %H:%M:%S}'.format(datetime.datetime.fromtimestamp(timestamp)) + ')\n'
    output_area.configure(state='normal')
    pos = "1.0" if begin else "end"
    output_area.insert(pos,data)
    output_area.see(pos)
    output_area.configure(state='disabled')

def clear_messages():
    output_area.configure(state='normal')
    output_area.delete('1.0', END)
    output_area.update()
    output_area.configure(state='disabled')
    cursor.execute('''DELETE FROM message''')
    db_conn.commit()
    
def handle_dbl_clk(event=None):
    #print('get_history', event)
    print('result_of_connect in handle_dbl_clk() is : ', result_of_connect)
    if result_of_connect==0:
        get_next_msg()
    else:
        from_local_db()
    output_area.see("1.0")
   
    

def clicked(event=None):
    #print('event',event)
    #txt.focus()
    r = hex(int(256 * random()))[2:]
    g = hex(int(256 * random()))[2:]
    b = hex(int(256 * random()))[2:]
    r = '0' * (2 - len(r)) + r
    g = '0' * (2 - len(g)) + g
    b = '0' * (2 - len(b)) + b
    rgb = '#' + r + g + b
    window.title("chatting")
    input_name = txt_name.get()
    input_msg = txt_msg.get()
    if txt_name.is_empty():
        messagebox.showinfo('ошибка ввода' , "Вы не ввели имя")
        return
    if txt_msg.is_empty():
        return
    btn.configure(text="Отправлено")
    #lbl.configure(text="введённый текст: "+ input_txt)
    #messagebox.showinfo('введённый текст' , input_txt)
    send_message(input_name, input_msg)
    #add_message(input_name, input_msg, datetime.datetime.fromtimestamp(time()))
    txt_msg.delete(0, END)
    window.after(3*10**3, lambda: btn.configure(text="Отправить"))


def change_users(number):
    text = lbl_users.cget("text")
    text = text.split(':')[0] + ': ' + str(number)
    lbl_users.config(text=text)

def preview_picture():
    global selected_image
    #aux = Toplevel()
    #aux.transient(window)
    #aux.title("Selected picture")
    input_path_picture = txt_picture.get()
    if txt_picture.is_empty():
        messagebox.showinfo('ошибка ввода пути' , "Вы не ввели путь")
        return
    try:
        img = Image.open(input_path_picture)
    except FileNotFoundError as err:
        messagebox.showinfo('ошибка пути к изображению' , "нет такого файла")
        return
    img_small = img.resize((PREVIEW_IMAGE_SMALL_SIZE, PREVIEW_IMAGE_SMALL_SIZE), Image.ANTIALIAS)
    img_large = img.resize((PREVIEW_IMAGE_LARGE_SIZE, PREVIEW_IMAGE_LARGE_SIZE), Image.ANTIALIAS)
    img_small = ImageTk.PhotoImage(img_small)
    img_large = ImageTk.PhotoImage(img_large)
    main_imgLabel._img_small = img_small
    main_imgLabel._img_large = img_large
    main_imgLabel.configure(image=img_small)
    if selected_image:
        selected_image.configure(bg="blue")
        selected_image = None
    btn_sending_picture.configure(state=NORMAL)
    
    
def resize_picture(imgLabel,event=None):
    global showing_image
    showing_image = not showing_image
    if showing_image:
        right_top_frame.pack_forget()
        new_img = imgLabel._img_large
    else:
        right_top_frame.pack(side=TOP, expand=0, fill=X)
        new_img = imgLabel._img_small
    imgLabel.configure(image=new_img)

def select_picture(imgLabel,event=None):
    global selected_image, showing_image
    if selected_image:
        selected_image.configure(bg="blue")
        if selected_image == imgLabel:
            selected_image = None
            main_imgLabel._img_small = empty_img_small
            main_imgLabel._img_large = empty_img_large
            showing_image = True
            resize_picture(main_imgLabel)
            return
    imgLabel.configure(bg="yellow")
    selected_image = imgLabel
    main_imgLabel._img_small = imgLabel._img_small
    main_imgLabel._img_large = imgLabel._img_large
    showing_image = True
    resize_picture(main_imgLabel)

def add_img_label(img):
    img_small = img.resize((PREVIEW_IMAGE_SMALL_SIZE, PREVIEW_IMAGE_SMALL_SIZE), Image.ANTIALIAS)
    img_large = img.resize((PREVIEW_IMAGE_LARGE_SIZE, PREVIEW_IMAGE_LARGE_SIZE), Image.ANTIALIAS)
    img_small = ImageTk.PhotoImage(img_small)
    img_large = ImageTk.PhotoImage(img_large)
    imgLabel = Label(canvas_frame, image=img_small, bg="blue")
    imgLabel._img_small = img_small
    imgLabel._img_large = img_large
    imgLabel.pack(fill='y', expand=False, side='right')
    imgLabel.bind("<Button-1>", partial(select_picture, imgLabel))
    canvas.update_idletasks()
    canvas.configure(scrollregion=canvas.bbox('all'), xscrollcommand=scroll_x.set)

def send_image():
    input_path_picture = txt_picture.get()
    if txt_picture.is_empty():
        messagebox.showinfo('ошибка ввода пути' , "Вы не ввели путь")
        return
    try:
        img = Image.open(input_path_picture)
    except FileNotFoundError as err:
        messagebox.showinfo('ошибка пути к изображению' , "нет такого файла")
        return
    name = txt_name.get()
    if not name:
        messagebox.showinfo('ошибка ввода имени' , "введите имя пользователя")
    if s is None: return
    with open(input_path_picture, 'rb') as f:
        file = f.read()
    #file = file.decode('iso-8859-1')
    file = base64.b64encode(file).decode()
    #print('тип отправляемого файла изображ', type(file))
    data = {'type': 'image', 'username': name,'file': file}
    #print('printing inserting','''INSERT INTO client_username_db VALUES (?)''', (data['username']))
    #cursor.execute('''INSERT INTO username VALUES (?,?)''', (data['username'], data['timestamp']))
    #db_conn.commit()
    add_img_label(img)
    send_data(data)
    btn_sending_picture.configure(state=DISABLED)

def _f(lo, hi):
    scroll_x.set(lo, hi)

def _g(*args, **kwargs):
    canvas.xview(*args, **kwargs)

def frames_append(input_data, frame_count, time_info, flags):
    global frames
    frames.append(input_data)
    return input_data, pyaudio.paContinue
    
  
def recording_audio():
    global WAVE_OUTPUT_FILENAME, audio_rec, stream_rec
    RECORD_SECONDS = 15
    if audio_rec is None:
        btn_record.configure(text="Recording", bg="yellow", fg="blue")
        WAVE_OUTPUT_FILENAME = str(random()) + WAVE_OUTPUT_FILENAME
        audio_rec = pyaudio.PyAudio()
        # start Recording
        stream_rec = audio_rec.open(format=FORMAT, channels=CHANNELS,
                rate=RATE, input=True,
                stream_callback=frames_append,
                frames_per_buffer=CHUNK)
        print('recording...')
    else:
        # stop Recording
        stream_rec.stop_stream()
        stream_rec.close()
        audio_rec.terminate()
        waveFile = wave.open(WAVE_OUTPUT_FILENAME, 'wb')
        waveFile.setnchannels(CHANNELS)
        waveFile.setsampwidth(audio_rec.get_sample_size(FORMAT))
        waveFile.setframerate(RATE)
        waveFile.writeframes(b''.join(frames))
        waveFile.close()
        stream_rec = None
        audio_rec = None
        btn_record.configure(text="Record", bg="yellow", fg="red")
        btn_sending_audio.configure(state=NORMAL)
        frames.clear()
    

def send_audio():
    name = txt_name.get()
    if txt_name.is_empty():
        messagebox.showinfo('ошибка ввода' , "Вы не ввели имя")
        return
    with open(WAVE_OUTPUT_FILENAME, 'rb') as f:
        file = f.read()
    file = base64.b64encode(file).decode()
    data = {'type': 'audio', 'username': name,'file': file}
    send_data(data)
    btn_sending_audio.configure(state=DISABLED)

def select_audio(filename, audioLabel, event=None):
    global audio_out, audio_out_stop, current_audioLabel, playing_event
    if audio_out == False:
        playing_event.wait()
        audio_out = True
        current_audioLabel = audioLabel
        playing_event.clear()
        thread=Thread(target=_select_audio, args = (filename, audioLabel))
        thread.start()
    else:
        audio_out_stop = True
        audio_out = False
        if current_audioLabel is not audioLabel:
            select_audio(filename, audioLabel, event)
            
            

def _select_audio(filename, audioLabel, event=None):
    global audio_out, audio_out_stop, playing_event
    audioLabel.configure(fg="blue", image=stop_img)
    chunk = 1024  
    f = wave.open(filename,"rb")   
    p = pyaudio.PyAudio()  
    stream = p.open(format = p.get_format_from_width(f.getsampwidth()),  
                channels = f.getnchannels(),  
                rate = f.getframerate(),  
                output = True)
    data = f.readframes(chunk)  
    while data:
        if audio_out_stop == True:
            break
        else:
            stream.write(data)  
            data = f.readframes(chunk)
    audio_out_stop = False
    audio_out = False
    stream.stop_stream()
    stream.close()
    p.terminate()
    playing_event.set()
    audioLabel.configure(fg="black", image=play_img)

    
   
    
    

def add_audio_label(username, filename):
    audioLabel = Label(canvas2_frame, image=play_img, text='      ' + username, bg="red", compound=LEFT, width=500)
    audioLabel.pack(fill='y', expand=False, side='bottom')
    audioLabel.bind("<Button-1>", partial(select_audio, filename, audioLabel))
    canvas2.update_idletasks()
    canvas2.configure(scrollregion=canvas2.bbox('all'), yscrollcommand=scroll_y.set)


selected_image = None     
showing_image = False
PREVIEW_IMAGE_SMALL_SIZE = 200
PREVIEW_IMAGE_LARGE_SIZE = 600
kw = 0.8
kh = 0.8
init_db()
window = Tk()
width=kw*window.winfo_screenwidth()
height=kh*window.winfo_screenheight()
x = (1 - kw) / 2*window.winfo_screenwidth()
y = (1 - kh) / 2*window.winfo_screenheight()
window.geometry('%dx%d+%d+%d' % (width, height, x, y))
#window.minsize(width=0.8*window.winfo_screenwidth(), height=0.8*window.winfo_screenheight())
#window.maxsize(width=0.8*window.winfo_screenwidth(), height=0.8*window.winfo_screenheight())
#print(window.winfo_screenheight())
window.title("chat")
#lbl_text = Label(window, text="echo server", font=("Arial Bold", 12))
#lbl_text.grid(column=0, row=1)
#lbl_name = Label(window, text="Username", font=("Arial Bold", 12))
#lbl_name.grid(column=0, row=1)
left_frame = Frame(window, relief=RIDGE, borderwidth=2)
left_frame.pack(side=LEFT)
right_frame = Frame(window, relief=RIDGE, borderwidth=2)
right_frame.pack(side=TOP, expand=1, fill=BOTH)
left_bottom_frame = Frame(left_frame, relief=RIDGE, borderwidth=2)
left_bottom_frame.pack(side=BOTTOM, expand=1, fill=BOTH)
left_top_frame = Frame(left_frame, relief=RIDGE, borderwidth=2)
left_top_frame.pack(side=TOP, expand=0, fill=X)

right_bottom_frame = Frame(right_frame, relief=RIDGE, borderwidth=2)
right_bottom_frame.pack(side=BOTTOM, expand=1, fill=BOTH)
right_top_frame = Frame(right_frame, relief=RIDGE, borderwidth=2)
right_top_frame.pack(side=TOP, expand=0, fill=X)

empty_img_large = Image.new('RGB', (PREVIEW_IMAGE_LARGE_SIZE,PREVIEW_IMAGE_LARGE_SIZE), (0, 0, 255))
empty_img_small = empty_img_large.resize((PREVIEW_IMAGE_SMALL_SIZE, PREVIEW_IMAGE_SMALL_SIZE), Image.ANTIALIAS)

empty_img_large = ImageTk.PhotoImage(empty_img_large)
empty_img_small = ImageTk.PhotoImage(empty_img_small)
main_imgLabel = Label(right_bottom_frame, image=empty_img_small)
main_imgLabel._img_small = empty_img_small
main_imgLabel._img_large = empty_img_large
main_imgLabel.pack(side = 'top', fill='y')
main_imgLabel.bind("<Button-1>", partial(resize_picture, main_imgLabel))

lbl_users = Label(right_top_frame, text="number of users: 4", font=("Arial Bold", 12))
lbl_users.pack(side=TOP)


btn = Button(right_top_frame, text="Отправить", bg="yellow", fg="red", command=clicked, state=DISABLED)
btn_preview = Button(right_top_frame, text="Preview", bg="yellow", fg="red", command=preview_picture)
#btn_preview.grid(column=6, row=2)
btn_sending_picture = Button(right_top_frame, text="Send picture", bg="yellow", fg="red", command=send_image, state=DISABLED)
#btn_sending_picture.grid(column=7, row=2, padx=50)
btn_record = Button(right_frame, text="Record", bg="yellow", fg="red", command=recording_audio)
btn_sending_audio = Button(right_frame, text="Send audio", bg="yellow", fg="red", command=send_audio, state=DISABLED)


try:
    cursor.execute('''SELECT * FROM username ORDER BY timestamp DESC LIMIT 1;''')
    username_from_db = cursor.fetchone()
    username_from_db = username_from_db['username']
except Exception as err:
    print('ошибка с чтением из бд', err)
#btn.grid(column=3, row=2)
txt_name = EntryWithPlaceholder(right_top_frame, placeholder="username")
if username_from_db is not None:
    txt_name.set_text(username_from_db)
    
##txt = Entry(window,width=10)
#txt_name.grid(column=0, row=2)
def handle_input(text1):
    #print(text1)
    if text1:
        btn.configure(state=NORMAL)
    else:
        btn.configure(state=DISABLED)
txt_msg = EntryWithPlaceholder(right_top_frame, placeholder="message", on_input=handle_input)
#txt_msg.grid(column=1, row=2)
txt_msg.bind('<Return>', clicked)
txt_picture = EntryWithPlaceholder(right_top_frame, placeholder="path to the picture")
#txt_picture.grid(column=5, row=2, padx=50, pady=20)
txt_picture.bind('<Return>', clicked)


output_area = scrolledtext.ScrolledText(left_top_frame,width=40,height=100, bg="yellow", fg="red", state=DISABLED)
output_area.bind('<Double-Button-1>', handle_dbl_clk)
#print(help(output_area))
#output_area.grid(column=0,row=3)

canvas = Canvas(right_bottom_frame, bg="yellow")
scroll_x = Scrollbar(right_bottom_frame, orient="horizontal", command=canvas.xview)


canvas_frame = Frame(canvas)
# group of widgets

   
# put the frame in the canvas
canvas.create_window(0, 0, anchor='nw', window=canvas_frame)

#for i in range(7):
#    Label(canvas_frame, text="I'm a button in the scrollable frame").pack(side='left')

# make sure everything is displayed before configuring the scrollregion
canvas.update_idletasks()

canvas.configure(scrollregion=canvas.bbox('all'), xscrollcommand=scroll_x.set)


scroll_x.pack(fill='x', side='bottom')
canvas.pack(fill='x', side='bottom')

play_img = Image.open('play-button.png')
play_img = play_img.resize((30, 30), Image.ANTIALIAS)
play_img = ImageTk.PhotoImage(play_img)

stop_img = Image.open('stop-button.jpeg')
stop_img = stop_img.resize((30, 30), Image.ANTIALIAS)
stop_img = ImageTk.PhotoImage(stop_img)

canvas2 = Canvas(left_bottom_frame, bg="red")
scroll_y = Scrollbar(left_bottom_frame, orient="vertical", command=canvas2.yview)



canvas2_frame = Frame(canvas2)
# group of widgets

# put the frame in the canvas
canvas2.create_window(0, 0, anchor='nw', window=canvas2_frame)

#for i in range(7):
#    Label(canvas_frame, text="I'm a button in the scrollable frame").pack(side='left')

#for i in range(30):
    #add_audio_label('user1', 'file.wav')
    #label = Label(canvas2, text='label %i' % i)
    #canvas2.create_window(0, i*50, anchor='nw', window=label, height=50)

# make sure everything is displayed before configuring the scrollregion
canvas2.update_idletasks()

canvas2.configure(scrollregion=canvas2.bbox('all'), yscrollcommand=scroll_y.set)

canvas2.pack(fill='y', side='left')
scroll_y.pack(fill='y', side='left')



txt_name.pack(side = 'left')
txt_msg.pack(side = 'left')
btn.pack(side = 'left')
txt_picture.pack(side = 'left')
btn_preview.pack(side = 'left')
btn_sending_picture.pack(side = 'left')
btn_record.pack(side = 'left') 
btn_sending_audio.pack(side = 'left')

output_area.pack(side = 'left')

print('current_page в итоге:', current_page)
print('current_page_local в итоге:', current_page_local)
from_local_db()
connect()
window.mainloop()




'''with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.connect_ex((HOST, PORT))
    result_of_connect = s.connect_ex((HOST, PORT))
    if result_of_connect == 22:
        print('result_of_connect', result_of_connect)
    print('result_of_connect', result_of_connect) '''


