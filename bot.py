import yfinance as yf
import pandas as pd
import time
import pandas_ta as ta
from telegram import Bot
import asyncio
from threading import Thread # 🚨 NOWY IMPORT DLA URUCHOMIENIA W TLE!

# --- Import wskaźników technicznych ---
import pandas_ta as pta 
# --------------------------------------

# ==================== USTAWIENIA FLASK DLA RENDER/GUNICORN ====================
from flask import Flask
# To jest ta instancja 'app', której szuka Gunicorn!
app = Flask(__name__) 

@app.route('/')
def home():
    # Render używa tego do sprawdzenia, czy serwer jest "live"
    return "Bot is running!"
# ==============================================================================


# ==================== USTAWIENIA TELEGRAMA ====================
# Uwaga: Render używa zmiennych środowiskowych, to są domyślne.
TELEGRAM_BOT_TOKEN = "8346426967:AAFboh8UQzHZfSRFW4qvXMGG2fzM0-DsO80"
TELEGRAM_CHAT_ID = "6703750254"
# =============================================================

# ----------------- USTAWIENIA MONITOROWANIA -----------------
SYMBOLS = [
    "EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X", "USDCHF=X", "NZDUSD=X",
    "EURGBP=X", "EURJPY=X", "EURAUD=X", "EURCAD=X", "EURCHF=X", "EURNZD=X",
    "GBPJPY=X", "GBPAUD=X", "GBPCAD=X", "GBPCHF=X", "GBPNZD=X",
    "AUDJPY=X", "CADJPY=X", "CHFJPY=X", "NZDJPY=X",
    "GC=F",          # Złoto
    "SI=F",          # Srebro
    "BTC-USD"        # Bitcoin
]
FRAMES = ["1h", "15m", "5m"]      # LISTA INTERWAŁÓW
STRATEGIES = ["SMA", "RSI", "MACD"] 
TP_RATIO = 2.0                    # Współczynnik Risk:Reward dla TP (R:R 1:2)
wait_time = 60 # 60 sekund 
# ------------------------------------------------------------

# ----------------- USTAWIENIA PARAMETRÓW WSZKAŹNIKÓW -----------------
SMA_FAST = 10
SMA_SLOW = 20
SMA_TREND_FILTER = 100 # 🚨 NOWY: Filtr trendu (długoterminowa średnia)
RSI_PERIOD = 14 
RSI_LOW_LEVEL = 30 
RSI_HIGH_LEVEL = 70 
# Parametry MACD
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
# --------------------------------------------------------------------

async def wyslij_alert(alert_text):
    """Wysyła alert za pomocą Telegrama asynchronicznie."""
    try:
        await Bot(token=TELEGRAM_BOT_TOKEN).send_message(
            chat_id=TELEGRAM_CHAT_ID, 
            text=alert_text, 
            parse_mode='HTML'
        )
        print("✅ ALERT WYSŁANY DO TELEGRAMA: " + alert_text)
    except Exception as e:
        print(f"❌ BŁĄD WYSYŁANIA TELEGRAMU: {e}")

def generuj_alert(wiersz, symbol, interwal, strategia, kierunek):
    """Formatuje i wysyła ładniejszy i bardziej szczegółowy alert sygnału."""
    
    # Krok 1: Bezpieczne pobranie kluczowych danych
    price = wiersz['Close'].item()
    
    # 🚨 POBIERANIE SL/TP
    sl_low_item = wiersz.get('RSI_SL_Low', pd.NA).item() if wiersz.get('RSI_SL_Low', pd.NA) is not pd.NA else None
    sl_high_item = wiersz.get('RSI_SL_High', pd.NA).item() if wiersz.get('RSI_SL_High', pd.NA) is not pd.NA else None

    sl_val = None
    
    if kierunek == "BUY":
        emoji = "🟢"
        sl_val = sl_low_item
    else: # SELL
        emoji = "🔴"
        sl_val = sl_high_item

    # Krok 2: Obliczanie SL i TP
    sl_text = "N/A"
    tp_text = "N/A"
    
    if sl_val is not None:
        try:
            sl_text = f"{sl_val:.5f}"
            
            # Obliczenie ryzyka/nagrody
            if kierunek == "BUY":
                risk = price - sl_val
                tp_val = price + risk * TP_RATIO
            else:
                risk = sl_val - price
                tp_val = price - risk * TP_RATIO
                
            tp_text = f"{tp_val:.5f}"
        except:
            sl_text = "Błąd SL"
            tp_text = "Błąd TP"

    # Krok 3: Szczegóły wskaźników (dodanie danych kontekstowych)
    # Użycie tagu <b> dla spójności HTML
    details = f"\n\n⚙️ <b>Szczegóły Wskaźników ({strategia})</b>:"
    
    if "SMA" in strategia:
        sma_fast = wiersz.get('SMA_Fast', pd.NA).item() if wiersz.get('SMA_Fast', pd.NA) is not pd.NA else "N/A"
        sma_slow = wiersz.get('SMA_Slow', pd.NA).item() if wiersz.get('SMA_Slow', pd.NA) is not pd.NA else "N/A"
        sma_trend = wiersz.get('SMA_Trend', pd.NA).item() if wiersz.get('SMA_Trend', pd.NA) is not pd.NA else "N/A"
        details += f"\n- SMA {SMA_FAST}/{SMA_SLOW}: <code>{sma_fast:.5f}</code> / <code>{sma_slow:.5f}</code>"
        details += f"\n- Filtr Trendu (SMA {SMA_TREND_FILTER}): <code>{sma_trend:.5f}</code>"
        
    if "RSI" in strategia:
        rsi_val = wiersz.get('RSI', pd.NA).item() if wiersz.get('RSI', pd.NA) is not pd.NA else "N/A"
        details += f"\n- RSI: <code>{rsi_val:.2f}</code> (Buy/Sell: {RSI_LOW_LEVEL}/{RSI_HIGH_LEVEL})"

    # MACD 
    if "MACD" in strategia or "Cnf" in strategia: 
        macd_name = 'MACD_Value'
        signal_name = 'MACDS_Value'
        
        macd_val = wiersz.get(macd_name, pd.NA).item() if wiersz.get(macd_name, pd.NA) is not pd.NA else "N/A"
        signal_val = wiersz.get(signal_name, pd.NA).item() if wiersz.get(signal_name, pd.NA) is not pd.NA else "N/A"
        details += f"\n- MACD/Signal: <code>{macd_val:.5f}</code> / <code>{signal_val:.5f}</code>"
        
    # Krok 4: Składanie gotowej wiadomości (Utrzymana kolejność i pogrubienie liczb)
    alert_text = (
        f"{emoji} <b>NOWY SYGNAŁ {kierunek}</b> ({strategia}) {emoji}\n"
        f"————————————————————\n"
        f"📊 <b>PARA:</b> <code>{symbol} / {interwal}</code>\n"
        f"\n"
        # 1. WEJŚCIE (bold)
        f"💰 <b>WEJŚCIE:</b> <b>{price:.5f}</b>\n" 
        # 2. TAKE PROFIT (bold)
        f"🎯 <b>TAKE PROFIT (R:R {TP_RATIO}):</b> <b>{tp_text}</b>\n" 
        # 3. STOP LOSS (bold)
        f"🛑 <b>STOP LOSS:</b> <b>{sl_text}</b> ({'Low' if kierunek == 'BUY' else 'High'} Poprz. Świecy)\n" 
        f"{details}"
    )

    # Wysłanie alertu
    asyncio.run(wyslij_alert(alert_text))


def pobierz_dane(symbol, interwal):
    """Pobiera historyczne dane OHLC z yfinance, bez agresywnego wstępnego czyszczenia."""
    try:
        data = yf.download(symbol, interval=interwal, period="60d", progress=False)
        if data.empty:
            return pd.DataFrame()  
        print(f"DEBUG: YF Pobrana długość dla {symbol} {interwal}: {len(data)}")    
        return data
        
    except Exception as e:
        print(f"❌ BŁĄD POBIERANIA DANYCH dla {symbol} ({interwal}): {e}")
        return pd.DataFrame()

def oblicz_wskaźniki_dodatkowe(data):
    """Oblicza wskaźniki za pomocą biblioteki pandas_ta, z gwarantowaną normalizacją kolumn."""
    
    data = data.copy()
    
    # --- Pobieranie wartości globalnych ---
    SMA_FAST_VAL = globals().get('SMA_FAST', 10)
    SMA_SLOW_VAL = globals().get('SMA_SLOW', 20)
    SMA_TREND_FILTER_VAL = globals().get('SMA_TREND_FILTER', 100) # 🚨 NOWA WARTOŚĆ
    RSI_PERIOD_VAL = globals().get('RSI_PERIOD', 14)
    
    MACD_FAST_VAL = globals().get('MACD_FAST', 12)
    MACD_SLOW_VAL = globals().get('MACD_SLOW', 26)
    MACD_SIGNAL_VAL = globals().get('MACD_SIGNAL', 9)

    try:
        # 1. NORMALIZACJA KOLUMN
        new_columns = []
        for col in data.columns:
            if isinstance(col, tuple): col_name = col[0] 
            elif isinstance(col, str) and col.startswith("('"):
                try: col_name = eval(col)[0] 
                except: col_name = col
            else: col_name = col
            new_columns.append(str(col_name).title())

        data.columns = new_columns
        
        if 'Close' not in data.columns:
             if 'Adj Close' in data.columns: data['Close'] = data['Adj Close']
             else: raise ValueError("Kolumna 'Close' jest pusta lub jej brakuje po ujednoliceniu.")

        # 2. Konwersja typów (WZMOCNIONA)
        data['Close'] = data.get('Close', pd.Series(dtype='float64')).astype('float64')
        data['Low'] = data.get('Low', pd.Series(dtype='float64')).astype('float64')
        data['High'] = data.get('High', pd.Series(dtype='float64')).astype('float64')

        if data['Close'].empty or data['Close'].isnull().all():
            raise ValueError(f"Kolumna 'Close' jest pusta po normalizacji. Dostępne kolumny: {data.columns.tolist()}")

        # 3. SMA 
        data['SMA_Fast'] = ta.sma(data['Close'], length=SMA_FAST_VAL)
        data['SMA_Slow'] = ta.sma(data['Close'], length=SMA_SLOW_VAL)
        data['SMA_Trend'] = ta.sma(data['Close'], length=SMA_TREND_FILTER_VAL) # 🚨 NOWY SMA
        
        data['SMA_Buy'] = (data['SMA_Fast'] > data['SMA_Slow']) & (data['SMA_Fast'].shift(1) <= data['SMA_Slow'].shift(1))
        data['SMA_Sell'] = (data['SMA_Fast'] < data['SMA_Slow']) & (data['SMA_Fast'].shift(1) >= data['SMA_Slow'].shift(1))
        
        # 4. RSI 
        data['RSI'] = ta.rsi(data['Close'], length=RSI_PERIOD_VAL)
        
        RSI_LOW_LEVEL_VAL = globals().get('RSI_LOW_LEVEL', 30)
        RSI_HIGH_LEVEL_VAL = globals().get('RSI_HIGH_LEVEL', 70)
        data['RSI_Buy'] = (data['RSI'].shift(1) < RSI_LOW_LEVEL_VAL) & (data['RSI'] >= RSI_LOW_LEVEL_VAL)
        data['RSI_Sell'] = (data['RSI'].shift(1) > RSI_HIGH_LEVEL_VAL) & (data['RSI'] <= RSI_HIGH_LEVEL_VAL)

        # 5. MACD 
        data.ta.macd(fast=MACD_FAST_VAL, slow=MACD_SLOW_VAL, signal=MACD_SIGNAL_VAL, append=True)
        
        macd_signature = f'_{MACD_FAST_VAL}_{MACD_SLOW_VAL}_{MACD_SIGNAL_VAL}'
        
        found_macd_name = next((col for col in data.columns if macd_signature in col and col.lower().startswith('macd_') and 'h_' not in col.lower()), None)
        found_signal_name = next((col for col in data.columns if macd_signature in col and col.lower().startswith('macds_')), None)
        
        if found_macd_name is None or found_signal_name is None:
             found_macd_name = next((col for col in data.columns if col.lower().startswith('macd_') and 'h_' not in col.lower()), None)
             found_signal_name = next((col for col in data.columns if col.lower().startswith('macds_')), None)
             
             if found_macd_name is None or found_signal_name is None:
                 raise ValueError(f"Kolumny MACD/MACDS nie zostały utworzone poprawnie. Dostępne kolumny: {data.columns.tolist()}")

        data['MACD_Value'] = data[found_macd_name]
        data['MACDS_Value'] = data[found_signal_name]
        
        # Logika MACD Crossover (do sygnałów filtrowanych)
        data['MACD_Buy'] = (data['MACD_Value'] > data['MACDS_Value']) & (data['MACD_Value'].shift(1) <= data['MACDS_Value'].shift(1))
        data['MACD_Sell'] = (data['MACD_Value'] < data['MACDS_Value']) & (data['MACD_Value'].shift(1) >= data['MACDS_Value'].shift(1))
        
        # 🚨 MACD KIERUNEK (Używany jako filtr konfluencji)
        data['MACD_Direction_Buy'] = data['MACD_Value'] >= data['MACDS_Value']
        data['MACD_Direction_Sell'] = data['MACD_Value'] <= data['MACDS_Value']
        
        # SL/TP bazujący na poprzedniej świecy
        data['RSI_SL_Low'] = data['Low'].shift(1)
        data['RSI_SL_High'] = data['High'].shift(1)
        
        # 6. Dodajemy kolumny 'Buy'/'Sell' jako typ Boolean (zabezpieczenie)
        data['SMA_Buy'] = data['SMA_Buy'].fillna(False)
        data['SMA_Sell'] = data['SMA_Sell'].fillna(False)
        data['RSI_Buy'] = data['RSI_Buy'].fillna(False)
        data['RSI_Sell'] = data['RSI_Sell'].fillna(False)
        data['MACD_Buy'] = data['MACD_Buy'].fillna(False) 
        data['MACD_Sell'] = data['MACD_Sell'].fillna(False) 
        
        print(f"DEBUG: ROZMIAR KOŃCOWY (PRZED RETURN): {len(data)}. Nazwy MACD: {found_macd_name}, {found_signal_name}")
        
        return data
        
    except Exception as e:
        print("🛑 BŁĄD W OBLICZANIU WSKAŹNIKÓW - SMA/RSI/MACD!")
        print(f"PEŁNY BŁĄD: {e}") 
        return pd.DataFrame()

def sprawdz_wszystkie_strategie(dane_ze_strategia, symbol, interwal):
    """Iteruje przez wszystkie sygnały w ostatniej świecy z uwzględnieniem filtracji."""
    
    if dane_ze_strategia.empty:
        return
        
    macd_name = 'MACD_Value'
    signal_name = 'MACDS_Value'

    kolumny_do_czyszczenia_NaN = ['Close', 'SMA_Slow', 'RSI', macd_name, 'SMA_Trend'] 
    
    try:
        if macd_name not in dane_ze_strategia.columns: return
        dane_czyste = dane_ze_strategia.dropna(subset=kolumny_do_czyszczenia_NaN).copy()
    except KeyError as e:
        print(f"🛑 BŁĄD DANYCH: Nie można znaleźć wszystkich kolumn wskaźników w DF dla {symbol} {interwal}.")
        return
    
    
    if dane_czyste.empty:
        print(f"OSTRZEŻENIE: Brak wystarczającej ilości danych do obliczenia wskaźników dla {symbol} {interwal}.")
        return

    # Krok 2: POBRANIE OSTATNIEGO WIERSZA DANYCH
    ostatni_wiersz = dane_czyste.iloc[-1]
    
    # 3. FILTRY
    
    # Filtr Trendu (SMA 100)
    trend_filter_buy = ostatni_wiersz['Close'].item() > ostatni_wiersz['SMA_Trend'].item()
    trend_filter_sell = ostatni_wiersz['Close'].item() < ostatni_wiersz['SMA_Trend'].item()
    
    # Filtr Konfluencji MACD (czy MACD jest powyżej/poniżej linii sygnału)
    macd_conf_buy = ostatni_wiersz['MACD_Direction_Buy'].item() 
    macd_conf_sell = ostatni_wiersz['MACD_Direction_Sell'].item() 

    
    # 4. SPRAWDZENIE SYGNAŁÓW Z NOWYMI WARUNKAMI

    # SPRAWDZENIE SMA Crossover (Wymaga Trendu i Konfluencji MACD)
    try:
        if ostatni_wiersz['SMA_Buy'].item() and trend_filter_buy and macd_conf_buy:
            generuj_alert(ostatni_wiersz, symbol, interwal, "SMA + MACD Cnf", "BUY")
            
        if ostatni_wiersz['SMA_Sell'].item() and trend_filter_sell and macd_conf_sell: 
            generuj_alert(ostatni_wiersz, symbol, interwal, "SMA + MACD Cnf", "SELL")
    except KeyError:
        pass 
        
    # SPRAWDZENIE RSI (Wymaga Trendu i Konfluencji MACD)
    try:
        if ostatni_wiersz['RSI_Buy'].item() and trend_filter_buy and macd_conf_buy: 
            generuj_alert(ostatni_wiersz, symbol, interwal, f"RSI + MACD Cnf", "BUY")
            
        if ostatni_wiersz['RSI_Sell'].item() and trend_filter_sell and macd_conf_sell:
            generuj_alert(ostatni_wiersz, symbol, interwal, f"RSI + MACD Cnf", "SELL")
    except KeyError:
        pass 
        
    # SPRAWDZENIE MACD Crossover (Wymaga Filtracji Trendu)
    try:
        if ostatni_wiersz['MACD_Buy'].item() and trend_filter_buy:
            generuj_alert(ostatni_wiersz, symbol, interwal, "MACD Crossover (Filtrowany)", "BUY")
            
        if ostatni_wiersz['MACD_Sell'].item() and trend_filter_sell:
            generuj_alert(ostatni_wiersz, symbol, interwal, "MACD Crossover (Filtrowany)", "SELL")
    except KeyError:
        pass
        
    return
    
# ==================== FUNKCJA GŁÓWNA PĘTLI SKANUJĄCEJ ====================
def skanuj_rynek_ciagle():
    """Główna funkcja zawierająca pętlę nieskończoną bota, zabezpieczona przed krytycznymi błędami."""
    
    # ------------------ 🛡️ BLOK BEZPIECZEŃSTWA 🛡️ ------------------
    try:
        # Wiadomość startowa bota do Telegrama
        print(f">>> BOT ALERT ZACZYNA PRACĘ. Monitoring {len(SYMBOLS)} par na {len(FRAMES)} interwałach i 3 strategiach! <<<")
        
        # Wysyłanie wiadomości testowej zaraz po starcie wątku
        start_message = (
            "       👁️     \n"
            "👑 **SO-ZE** 👑\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "✅ **BOT STARTUJE!** Usługa Render aktywna 24/7.\n"
            f"⏳ **NOWY** interwał skanowania: {wait_time} sekund."
        )
        # Używamy asyncio.run, ponieważ funkcja wyslij_alert jest asynchroniczna
        asyncio.run(wyslij_alert(start_message))
        
        while True:
            print(f"\n--- Rozpoczynam cykl skanowania ({pd.Timestamp.now().strftime('%H:%M:%S')}) ---")
            
            for symbol in SYMBOLS: 
                for frame in FRAMES:
                    try:
                        dane = pobierz_dane(symbol, frame)
                        if dane.empty: continue
                        dane_ze_strategia = oblicz_wskaźniki_dodatkowe(dane)
                        
                        print(f"DEBUG: Rozmiar DF dla {symbol} na {frame}: {len(dane_ze_strategia)}")
                        
                        if not dane_ze_strategia.empty:
                            print(f"-> Sprawdzam sygnały dla {symbol} na {frame}") 
                            sprawdz_wszystkie_strategie(dane_ze_strategia, symbol, frame)
                            
                    except Exception as e:
                        # Ten blok łapie błędy dla pojedynczej pary
                        print(f"❌ Wystąpił nieoczekiwany błąd w pętli dla {symbol} ({frame}): {e}")
            
            print(f"--- Cykl zakończony. Czekam {wait_time} sekund. ---")
            time.sleep(wait_time)
            
    except Exception as e:
        # 🚨 KRYTYCZNY BLOK: Łapie błąd, który zabił wątek!
        awaria_msg = f"🛑 KRYTYCZNY BŁĄD ZABIŁ WĄTEK SKANOWANIA! Bot przestał działać. Błąd: {e}"
        print(awaria_msg)
        # Wysyłamy alert o awarii na Telegrama
        asyncio.run(wyslij_alert(awaria_msg))
        # ------------------------------------------------------------------
        
        print(f"--- Cykl zakończony. Czekam {wait_time} sekund. ---")
        time.sleep(wait_time)


# ==================== URUCHOMIENIE BOTA W TLE (DLA RENDER) ====================
# Wywołanie funkcji start_bot_in_background, która uruchamia skanowanie w osobnym wątku.
def start_bot_in_background():
    """Uruchamia główną funkcję bota w tle, aby Gunicorn mógł działać jako serwer WWW."""
    t = Thread(target=skanuj_rynek_ciagle)
    t.start()

start_bot_in_background() # <--- To jest jedyne wywołanie kodu, które działa w głównym procesie!
# ==============================================================================

# UWAGA: Usunięto: if __name__ == "__main__":, ponieważ nie jest potrzebne na Renderze.







