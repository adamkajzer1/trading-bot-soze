import yfinance as yf
import time
import requests
import asyncio
import os
import random
import json
from datetime import datetime
from collections import deque

# --- KONFIGURACJA BOTA ---

# 1. Zmień na swój token bota Telegram
TELEGRAM_BOT_TOKEN = "Wpisz_Tutaj_Swój_Token"
# 2. Zmień na swój ID czatu Telegram
TELEGRAM_CHAT_ID = "Wpisz_Tutaj_Swój_ChatID"

# 3. Lista symboli do monitorowania (przykłady)
# Pamiętaj: Wymagany jest suffix "=X" dla par Forex i ".L" dla akcji.
SYMBOLS = [
    "EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", 
    "USDCAD=X", "USDCHF=X", "EURGBP=X",
    "GC=F", "SI=F", # Surowce (Złoto, Srebro)
    "BTC-USD", # Kryptowaluty
    "AAPL", "MSFT" # Akcje (bez sufixu)
]

# 4. Interwał odświeżania danych ('1m', '2m', '5m', '15m', '30m', '60m', '90m', '1h', '1d', '5d', '1wk', '1mo', '3mo')
# Błąd w logach sugeruje, że używasz '1m' - to jest bardzo obciążające dla serwera. 
# Zmień to na np. '5m' lub '15m', jeśli nie potrzebujesz ultraszybkiej analizy.
INTERWAL = '1m'

# 5. Parametry strategii (Moving Averages)
SHORT_MA_PERIOD = 20
LONG_MA_PERIOD = 50

# 6. Zarządzanie Ryzykiem
# Współczynnik Risk:Reward (np. 1.5 oznacza TP jest 1.5x większy niż SL)
RR_RATIO = 1.5 
# Procent ATR użyty do określenia Stop Loss (np. 1.0 oznacza, że SL jest równy 1x ATR)
ATR_MULTIPLIER = 1.0 
# Okres dla obliczenia Average True Range (ATR)
ATR_PERIOD = 14 


# --- GLOBALNE ZMIENNE STANU ---
# Używamy tej listy, aby zapobiec wielokrotnemu wysyłaniu tego samego sygnału
SENT_SIGNALS = {} # Format: {symbol: last_signal_timestamp}
# Używamy deque do przechowywania ostatnich logów (dla funkcji /logs)
LOG_HISTORY = deque(maxlen=50)

# --- FUNKCJE POMOCNICZE ---

def log(message):
    """Zapisuje wiadomość w konsoli i historii logów."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {message}"
    print(log_entry)
    LOG_HISTORY.append(log_entry)

def send_telegram_message(text):
    """Wysyła wiadomość do Telegrama."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': text,
        'parse_mode': 'Markdown' 
    }
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status() 
    except requests.exceptions.RequestException as e:
        log(f"Błąd wysyłania wiadomości Telegram: {e}")

def calculate_pips(symbol, value):
    """Oblicza liczbę pipsów dla danej wartości cenowej."""
    
    # 1. Określenie precyzji (liczby miejsc po przecinku)
    if "JPY" in symbol or "GC=F" in symbol:
        # Pary z JPY i niektóre surowce (Złoto) mają 2 lub 3 miejsca (np. 123.456). Pip = 0.01.
        pip_value = 0.01
        multiplier = 100
    elif "BTC" in symbol or symbol not in ["EURUSD=X", "GBPUSD=X", "AUDUSD=X"]:
         # Kryptowaluty, akcje, inne surowce - używamy stałej wartości pipsa (0.0001) dla ujednolicenia lub 0.01 dla ułamków
        if symbol in ["SI=F"]: # Srebro
             pip_value = 0.01 
             multiplier = 100
        elif symbol in ["AAPL", "MSFT"]: # Akcje
             pip_value = 0.01 
             multiplier = 100
        elif "BTC" in symbol: # Kryptowaluty
             # Dla uproszczenia (zbyt duża zmienność) - przyjmujemy, że 1 USD to 1 pip, ale to b. duże uproszczenie
             pip_value = 1.0
             multiplier = 1.0
        else:
            # Domyślnie dla większości walut (5-cyfrowe, pip = 0.0001)
            pip_value = 0.0001
            multiplier = 10000
    else:
        # Główne pary (EURUSD, GBPUSD, AUDUSD itp.) - 5 cyfr po przecinku, pip = 0.0001
        pip_value = 0.0001
        multiplier = 10000
    
    # Obliczenie wartości w pipsach (zaokrąglone do 2 miejsc)
    return round(value * multiplier, 2)


# --- GŁÓWNA LOGIKA HANDLOWA ---

def get_data(symbol, interwal):
    """
    Pobiera dane historyczne dla symbolu.
    DODANO FIX DLA PROBLEMU Z DANYMI '1m'
    """
    
    # Ustawienie okresu pobierania: 7 dni dla 1m, 60 dni dla reszty (aby uniknąć błędu API)
    if interwal == '1m':
        period = "7d"  # BEZPIECZNY OKRES DLA DANYCH 1-MINUTOWYCH
    else:
        period = "60d"
        
    try:
        # Linia 209 z logów (teraz 217)
        data = yf.download(symbol, interval=interwal, period=period, progress=False) 
        
        if data.empty:
            log(f"Brak danych dla symbolu {symbol}. Pomijanie.")
            return None
        return data
    except Exception as e:
        log(f"Nie udało się pobrać danych dla {symbol}: {e}")
        return None

def calculate_indicators(data):
    """Oblicza średnie kroczące i ATR."""
    # Średnie kroczące
    data['MA_Short'] = data['Close'].rolling(window=SHORT_MA_PERIOD).mean()
    data['MA_Long'] = data['Close'].rolling(window=LONG_MA_PERIOD).mean()
    
    # Average True Range (ATR)
    # True Range (TR)
    data['High-Low'] = data['High'] - data['Low']
    data['High-PrevClose'] = abs(data['High'] - data['Close'].shift(1))
    data['Low-PrevClose'] = abs(data['Low'] - data['Close'].shift(1))
    data['TR'] = data[['High-Low', 'High-PrevClose', 'Low-PrevClose']].max(axis=1)
    # ATR (EMA based)
    data['ATR'] = data['TR'].ewm(span=ATR_PERIOD, adjust=False).mean()
    
    return data

def check_for_signal(symbol, data):
    """
    Sprawdza, czy wystąpiło przecięcie średnich kroczących (sygnał kupna/sprzedaży).
    """
    # Upewnij się, że mamy wystarczającą ilość danych do obliczeń
    if len(data) < LONG_MA_PERIOD + ATR_PERIOD:
        log(f"Niewystarczająca ilość danych dla {symbol}. Wymagane co najmniej {LONG_MA_PERIOD + ATR_PERIOD} świec.")
        return None

    # Pobranie ostatniego w pełni ukształtowanego słupka (przedostatni w danych)
    last_idx = -2
    
    # Wartości dla ostatniego w pełni ukształtowanego słupka
    ma_short_prev = data['MA_Short'].iloc[last_idx - 1]
    ma_long_prev = data['MA_Long'].iloc[last_idx - 1]
    
    # Wartości dla obecnego, w pełni ukształtowanego słupka
    ma_short_curr = data['MA_Short'].iloc[last_idx]
    ma_long_curr = data['MA_Long'].iloc[last_idx]
    close_price = data['Close'].iloc[last_idx]
    atr_value = data['ATR'].iloc[last_idx]

    signal = None

    # SYGNAŁ KUPNA (BUY)
    # Krótka MA (20) przecina Długą MA (50) od dołu do góry
    if ma_short_prev <= ma_long_prev and ma_short_curr > ma_long_curr:
        signal = "KUPNO (BUY)"
        # Ustalenie poziomów SL/TP
        stop_loss = round(close_price - (atr_value * ATR_MULTIPLIER), 5)
        take_profit = round(close_price + (atr_value * ATR_MULTIPLIER * RR_RATIO), 5)
        action = "Long (Kup)"
        
    # SYGNAŁ SPRZEDAŻY (SELL)
    # Krótka MA (20) przecina Długą MA (50) od góry do dołu
    elif ma_short_prev >= ma_long_prev and ma_short_curr < ma_long_curr:
        signal = "SPRZEDAŻ (SELL)"
        # Ustalenie poziomów SL/TP
        stop_loss = round(close_price + (atr_value * ATR_MULTIPLIER), 5)
        take_profit = round(close_price - (atr_value * ATR_MULTIPLIER * RR_RATIO), 5)
        action = "Short (Sprzedaj)"
    
    # Jeśli znaleziono sygnał
    if signal:
        # Obliczenie pipsów do SL i TP
        sl_diff = abs(stop_loss - close_price)
        tp_diff = abs(take_profit - close_price)
        sl_pips = calculate_pips(symbol, sl_diff)
        tp_pips = calculate_pips(symbol, tp_diff)
        
        # Sprawdzenie, czy sygnał nie został już wysłany w tej świecy
        current_time = data.index[last_idx]
        
        if symbol not in SENT_SIGNALS or SENT_SIGNALS[symbol] < current_time:
            SENT_SIGNALS[symbol] = current_time
            
            # Formatuje i zwraca wiadomość do Telegrama
            message = (
                f"🚨 *NOWY SYGNAŁ HANDLOWY - {INTERWAL}* 🚨\n\n"
                f"📊 *PARA WALUTOWA/AKCJA:* `{symbol}`\n"
                f"📈 *AKCJA:* {action} ({signal})\n"
                f"💰 *CENA WEJŚCIA:* {close_price:.5f} (Zamknięcie świecy {current_time.strftime('%Y-%m-%d %H:%M')})\n"
                f"🛑 *STOP LOSS:* {stop_loss:.5f} ({sl_pips} pips)\n"
                f"🎯 *TAKE PROFIT (R:R {RR_RATIO}):* {take_profit:.5f} ({tp_pips} pips)\n"
                f"---"
            )
            return message
        else:
            log(f"Sygnał dla {symbol} w czasie {current_time} został już wysłany. Pomijanie.")
            return None

    return None

def main_loop():
    """Główna pętla programu."""
    log("Inicjalizacja bota. Rozpoczynanie pętli głównej...")
    
    # Wymuś wstępne wysłanie wiadomości na start
    send_telegram_message(
        f"🤖 Bot handlowy WŁĄCZONY.\n"
        f"Monitorowane interwały: `{INTERWAL}`.\n"
        f"Liczba par: {len(SYMBOLS)}."
    )

    while True:
        log("--- Rozpoczynanie cyklu skanowania ---")
        
        # Losowa kolejność symboli (aby uniknąć problemu z limitem zapytań API)
        random.shuffle(SYMBOLS)
        
        for symbol in SYMBOLS:
            log(f"Analiza symbolu: {symbol}")
            
            # 1. Pobierz dane
            data = get_data(symbol, INTERWAL)
            if data is None:
                continue

            # 2. Oblicz wskaźniki
            data = calculate_indicators(data)
            
            # 3. Sprawdź sygnał
            signal_message = check_for_signal(symbol, data)
            
            # 4. Wyślij alert, jeśli sygnał jest nowy
            if signal_message:
                log(f"ZNALEZIONO SYGNAŁ dla {symbol}. Wysyłanie alertu...")
                send_telegram_message(signal_message)
            
            # Odczekaj krótko między żądaniami, aby zmniejszyć obciążenie API
            time.sleep(1) 

        log("Cykl skanowania zakończony. Oczekiwanie na następny cykl...")
        # Czas oczekiwania przed kolejnym cyklem (np. 60 sekund)
        time.sleep(60) 

if __name__ == "__main__":
    # Inicjalizacja: Używamy asynchroniczności, aby uniknąć problemów z blokowaniem (opcjonalnie)
    # W prostych botach na PythonAnywhere wystarczy zwykła pętla while True.
    main_loop()

