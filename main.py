import telebot
from telebot import types
import pandas as pd
import random
import os
import sqlite3
import time
import threading
from flask import Flask, request

# --- SOZLAMALAR ---
API_TOKEN = '8490998299:AAEKIQQHwFbSboUsPTiu5FpzqWRFDuldb0g' 
ADMIN_ID = 7201215484 # <-- O'Z ID RAQAMINGIZNI YOZING
CHANNEL_USERNAME = '@Binary_Mind_Uz'

bot = telebot.TeleBot(API_TOKEN)
server = Flask(__name__) # Web server

# --- BAZA VA YORDAMCHI FUNKSIYALAR ---
def init_db():
    conn = sqlite3.connect('bot_users.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, joined_date TEXT)')
    conn.commit()
    conn.close()

def add_user_to_db(user_id):
    conn = sqlite3.connect('bot_users.db', check_same_thread=False)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT OR IGNORE INTO users (user_id, joined_date) VALUES (?, datetime('now'))", (user_id,))
        conn.commit()
    except: pass
    conn.close()

def get_all_users():
    conn = sqlite3.connect('bot_users.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users

# --- FLASK (WEBSAYT QISMI - UYG'OQ TURISHI UCHUN) ---
@server.route('/')
def webhook():
    bot.remove_webhook()
    bot.set_webhook(url='https://YOUR_APP_NAME.onrender.com/' + API_TOKEN)
    return "Bot ishlamoqda!", 200

@server.route('/ping')
def ping():
    return "Pong", 200

def run_flask():
    # Render bergan portda ishlash
    port = int(os.environ.get("PORT", 5000))
    server.run(host="0.0.0.0", port=port)

# --- BOT FUNKSIYALARI (Qisqartirilgan) ---
user_data = {}

def check_subscription(user_id):
    try:
        status = bot.get_chat_member(CHANNEL_USERNAME, user_id).status
        if status in ['left', 'kicked']: return False
        return True
    except: return False

def read_excel_quiz(file_path):
    try:
        df = pd.read_excel(file_path, header=None)
        questions = []
        for index, row in df.iterrows():
            row = row.dropna()
            if len(row) < 2: continue
            question_text = str(row[0]) 
            correct_answer = str(row[1]) 
            wrong_answers = [str(x) for x in row[2:].tolist()] 
            all_answers = [correct_answer] + wrong_answers
            random.shuffle(all_answers)
            try:
                correct_option_id = all_answers.index(correct_answer)
                questions.append({'question': question_text, 'options': all_answers, 'correct_option_id': correct_option_id})
            except: pass
        return questions
    except: return None

@bot.message_handler(commands=['start'])
def send_welcome(message):
    add_user_to_db(message.from_user.id)
    if not check_subscription(message.from_user.id):
        bot.send_message(message.chat.id, f"Iltimos {CHANNEL_USERNAME} ga a'zo bo'ling.")
        return
    bot.send_message(message.chat.id, "Excel fayl yuboring.")

@bot.message_handler(content_types=['document'])
def handle_docs(message):
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        file_name = f"quiz_{message.chat.id}.xlsx"
        with open(file_name, 'wb') as new_file: new_file.write(downloaded_file)
        questions = read_excel_quiz(file_name)
        os.remove(file_name)
        
        if not questions:
            bot.reply_to(message, "Xatolik.")
            return

        random.shuffle(questions)
        user_data[message.chat.id] = {'all_questions': questions, 'total': len(questions), 'score': 0, 'idx': 0, 'limit': len(questions), 'timer': 15}
        
        bot.send_message(message.chat.id, "Test boshlandi! 15 soniya vaqt.")
        send_next_question(message.chat.id)
    except Exception as e:
        bot.reply_to(message, f"Xato: {e}")

def send_next_question(chat_id):
    data = user_data.get(chat_id)
    if not data: return
    if data['idx'] >= data['limit']:
        bot.send_message(chat_id, f"Tugadi! Natija: {data['score']}/{data['limit']}")
        del user_data[chat_id]
        return
    
    q = data['all_questions'][data['idx']]
    bot.send_poll(chat_id, f"{data['idx']+1}. {q['question']}", q['options'], type='quiz', correct_option_id=q['correct_option_id'], open_period=data['timer'], is_anonymous=False)

@bot.poll_answer_handler()
def handle_poll(poll):
    uid = poll.user.id
    if uid in user_data:
        data = user_data[uid]
        q = data['all_questions'][data['idx']]
        if poll.option_ids[0] == q['correct_option_id']: data['score'] += 1
        data['idx'] += 1
        send_next_question(uid)

@bot.message_handler(commands=['send'])
def send_broadcast(message):
    if message.from_user.id != ADMIN_ID: return
    users = get_all_users()
    for u in users:
        try: bot.send_message(u, message.text.replace('/send', ''))
        except: pass
    bot.reply_to(message, "Yuborildi.")

if __name__ == '__main__':
    init_db()
    # Botni alohida oqimda ishlatish
    t = threading.Thread(target=bot.infinity_polling)
    t.start()
    # Flask serverni ishlatish
    run_flask()