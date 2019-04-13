from threading import Thread
import socket
import sys
from time import sleep,time
import json
import sqlite3
import uuid
import base64
import os.path

clients=[]
#messages=[]

IMAGE_FOLDER = os.path.join(os.getcwd(), 'images')

def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

db_conn = sqlite3.connect('example.db', check_same_thread=False)
db_conn.row_factory = dict_factory
cursor = db_conn.cursor()

def get_all_messages(timestamp=1e+12):
    cursor.execute('SELECT * FROM message WHERE timestamp < {0} ORDER BY timestamp DESC LIMIT 20;'.format(timestamp))
    #print('SELECT * FROM message WHERE timestamp < {0} ORDER BY timestamp DESC LIMIT 20;'.format(timestamp))
    messages = cursor.fetchall()
    return messages

def get_all_images():
    cursor.execute('SELECT * FROM image ORDER BY timestamp;')
    images = cursor.fetchall()
    return images


def init_db():
    cursor.execute('''CREATE TABLE IF NOT EXISTS message(id integer primary key, username text, text text, timestamp real)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS image(id integer primary key, username text, filename text, timestamp real)''')
    db_conn.commit()


def send_amount_users():
    data = {'type': 'users', 'amount': len(clients)}
    send_to_all(data)

def send_to_all(data):
    data = json.dumps(data).encode('utf-8') + b'\x00'
    for client in clients:
        #print('sending to client', client)
        try:
            print('отправляем клиенту')
            client.sendall(data)
        except Exception as err:
            print('ERROR in sending_all', err)
            
def send_to_client(client, data):
    try:
        data = json.dumps(data).encode('utf-8') + b'\x00'
        client.sendall(data)
    except Exception as err:
        print('ERROR in sending_client', err)
    

def handler(conn, data):
    if data.get('type') == 'message':
        #print('получение сообщения от клиента:', data)
        data['timestamp'] = time()
        print('printing inserting', '''INSERT INTO message VALUES (NULL, '{username}', '{text}', {timestamp})'''.format(username=data['username'], text=data['text'], timestamp=data['timestamp']))
        cursor.execute('''INSERT INTO message VALUES (NULL, ?, ?, {timestamp})'''.format(timestamp=data['timestamp']), (data['username'], data['text']))
        db_conn.commit()
        #messages.append(data)
        send_to_all(data)
    elif data.get('type') == 'image':
        data['timestamp'] = time()
        print('image received')
        raw = data['file']
        file = base64.b64decode(raw)
        filename = str(uuid.uuid1())+'.jpg'
        full_filename = os.path.join(IMAGE_FOLDER, filename)
        with open(full_filename, 'wb') as tst:
            tst.write(file)
        cursor.execute('''INSERT INTO image VALUES (NULL, ?, ?, {timestamp})'''.format(timestamp=data['timestamp']), (data['username'], filename))
        db_conn.commit()
        send_to_all(data)
    elif data.get('type') == 'get_image':
        filename = data['filename']
        full_filename = os.path.join(IMAGE_FOLDER, filename)
        if not os.path.isfile(full_filename):
            #print('file not found')
            return
        with open(full_filename, 'rb') as tst:
            image_raw = tst.read()
        text = base64.b64encode(image_raw).decode()
        data = {'type': "get_image",'file': text}
        send_to_client(conn, data)
    elif data.get('type') == 'last_messages':
        messages = get_all_messages(data.get('timestamp'))
        data = {'type': "last_messages",'messages': messages}
        send_to_client(conn, data)
    elif data.get('type') == 'audio':
        print('audio received')
        send_to_all(data)
    
    
def listener(conn, addr):
    send_amount_users()
    print('listener started', addr)
    messages = get_all_messages()
    print('messages в listener', messages)
    data = {'type': "last_messages",'messages': messages}
    send_to_client(conn, data)
    images = get_all_images()
    data = {'type': "last_images",'images': images}
    send_to_client(conn, data)
    with conn:
        print('Connected to listener from', addr)
        data = b''
        while True:
            chunk = conn.recv(1024)
            if not chunk:
                print('no data in listener from client')
                for client in clients:
                    if client == conn:
                        try:
                            clients.remove(conn)
                        except ValueError:
                            print('что-то не то со списком клинетов в conn')
                        print("conn", conn)
                        print("clients", clients)
                
                send_amount_users()
                break
            
            #print('data received by listener', chunk.decode('utf-8'))
            #sleep(1.5)
            data += chunk
            while b'\x00' in data:
                ind = data.index(b'\x00')
                result = data[:ind]
                result = json.loads(result.decode('utf-8'))
                data = data[ind+1:]
                handler(conn, result)



if len(sys.argv) > 1:
    PORT = int(sys.argv[1])
else:
    PORT = 50082

HOST = ''

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.bind((HOST, PORT))
    #print('server starting on port', PORT)
    #data = s.recv(1024)
    s.listen(1)
    print('server starting on port', PORT)
    init_db()
    while True:
        conn, addr = s.accept()
        print('conn', conn)
        print('addr', addr)
        clients.append(conn)
        print('current clients', clients)
        th = Thread(target=listener, args=(conn, addr))
        th.start()
    
    
    
