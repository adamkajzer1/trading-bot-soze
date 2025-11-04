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
TELEGRAM_BOT_TOKEN = "8346426967:AAFboh8UQzHZsRFW4qvXMGG2fzM0-DsO80"
TELEGRAM_CHAT_ID = "6703750254"
# =============================================================

# ----------------- USTAWIENIA MONITOROWANIA (SCALPING) -----------------
SYMBOLS = [
    "EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X", "USDCHF=X", "NZDUSD=X",
    "EURGBP=X", "EURJPY=X", "EURAUD=X", "EURCAD=X", "EURCHF=X", "EURNZD=X",
    "GBPJPY=X", "GBPAUD=X", "GBPCAD=X", "GBPCHF=X", "GBPNZD=X",
    "AUDJPY=X", "CADJPY=X", "CHFJPY=X", "NZDJPY=X",
    "GC=F",          # Złoto
    "SI=F",          # Srebro
    "BTC-USD"        # Bitcoin
]
# 🚨 ZMIANA NA SCALPING: SZYBKIE INTERWAŁY
FRAMES = ["5m", "1m"]      # LISTA INTERWAŁÓW - TYLKO 5M I 1M
STRATEGIES = ["SMA", "RSI", "MACD"] 
# 🚨 ZMIANA NA SCALPING: BARDZO NISKI R:R
TP_RATIO = 1.2             # Współczynnik Risk:Reward dla TP (R:R 1:1.2) - Bardzo niski
wait_time = 60 # 60 sekund 
MIN_RISK = 0.00005 # Minimalne akceptowalne ryzyko (np. 5 pipsów)
# ------------------------------------------------------------

# ----------------- USTAWIENIA PARAMETRÓW WSZKAŹNIKÓW (SCALPING) -----------------
# 🚨 ZMIANA NA SZYBKIE SMA
SMA_FAST = 5
SMA_SLOW = 12
SMA_TREND_FILTER = 50 # 🚨 NOWY: Filtr trendu (długoterminowa średnia)
# 🚨 ZMIANA NA SZYBKIE RSI
RSI_PERIOD = 9 
RSI_LOW_LEVEL = 30 
RSI_HIGH_LEVEL = 70 
# Parametry MACD
# 🚨 ZMIANA NA SZYBKIE MACD
MACD_FAST = 7
MACD_SLOW = 14
MACD_SIGNAL = 5
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

def generuj_alert(wiersz, symbol, interwal, strategia, kierunek, sl_val):
    """Formatuje i wysyła ładniejszy i bardziej szczegółowy alert sygnału.
        Dodano obliczenia pipsów dla SL i TP."""
    
    # Krok 1: Bezpieczne pobranie kluczowych danych
    price = wiersz['Close'].item()
    
    sl_text = "N/A"
    tp_text = "N/A"
    risk_pips = "N/A"
    reward_pips = "N/A"
    
    if kierunek == "BUY":
        emoji = "🟢"
        sl_basis = "Low"
    else: # SELL
        emoji = "🔴"
        sl_basis = "High"

    # Krok 2: Obliczanie SL, TP, PIPSÓW RYZYKA/ZYSKU
    if sl_val is not None:
        try:
            # ===================== POPRAWIONA LOGIKA RYZYKA =====================
            # Ryzyko musi być zawsze dodatnią odległością.
            risk = abs(price - sl_val) 
            
            # Zabezpieczenie przed zerowym ryzykiem zostało już wykonane wcześniej
            if risk == 0:
                raise ValueError("Ryzyko jest zerowe. Błąd danych SL.")

            # Obliczenie TP na podstawie kierunku i pozytywnego ryzyka (risk)
            if kierunek == "BUY":
                # Dla BUY: TP = WEJŚCIE + RYZYKO_ABS * R:R
                tp_val = price + risk * TP_RATIO
            else: # SELL
                # Dla SELL: TP = WEJŚCIE - RYZYKO_ABS * R:R
                tp_val = price - risk * TP_RATIO
            # =================================================================
            
            # 🚨 OBLICZENIA PIPSÓW DLA FORMAOWANIA LOGÓW I WIZUALIZACJI
            
            # Sprawdzenie, czy to JPY (tylko 2 miejsca po przecinku)
            # W yfinance JPY to 3 miejsca po przecinku, 1 pip = 0.01
            if symbol.endswith("JPY=X") or symbol == "USDJPY=X" or symbol.endswith("JPY"):
                pips_multiplier = 100 # JPY: 0.01 = 1 PIP
                decimals = 3 # Trzy miejsca po przecinku dla JPY
            elif symbol in ["GC=F", "SI=F"]:
                # Metale i inne, mogą wymagać innej precyzji, na razie zostawiamy standard
                pips_multiplier = 10000 
                decimals = 5
            else:
                pips_multiplier = 10000 # Standard Forex: 0.0001 = 1 PIP
                decimals = 5 # Pięć miejsc po przecinku dla EURUSD (wliczając pipetę)
                
            # Poprawna konwersja do PIPSÓW: (absolutna odległość * mnożnik)
            risk_pips_val = risk * pips_multiplier
            reward_pips_val = risk_pips_val * TP_RATIO
            
            risk_pips = f"{risk_pips_val:.1f} pips"
            reward_pips = f"{reward_pips_val:.1f} pips"
            
            sl_text = f"{sl_val:.{decimals}f}"
            tp_text = f"{tp_val:.{decimals}f}"
            
        except ValueError as ve:
            print(f"BŁĄD W GENEROWANIU ALERTU RYZYKA: {ve}")
            sl_text = "Błąd SL"
            tp_text = "Błąd TP"
        except Exception as e:
            print(f"Nieoczekiwany błąd obliczeń SL/TP: {e}")
            sl_text = "Błąd SL"
            tp_text = "Błąd TP"

    # Krok 3: Szczegóły wskaźników (dodanie danych kontekstowych)
    # Użycie tagu <b> dla spójności HTML
    details = f"\n\n⚙️ <b>Szczegóły Wskaźników ({strategia})</b>:"
    
    # Precyzja formatowania dla wskaźników (jak dla ceny)
    # Użycie funkcji .get() z pd.NA jest bezpieczniejsze
    
    if "SMA" in strategia:
        sma_fast = wiersz.get('SMA_Fast', pd.NA).item() if wiersz.get('SMA_Fast', pd.NA) is not pd.NA else "N/A"
        sma_slow = wiersz.get('SMA_Slow', pd.NA).item() if wiersz.get('SMA_Slow', pd.NA) is not pd.NA else "N/A"
        sma_trend = wiersz.get('SMA_Trend', pd.NA).item() if wiersz.get('SMA_Trend', pd.NA) is not pd.NA else "N/A"
        
        # Formatowanie liczb z poprawną precyzją
        if isinstance(sma_fast, float): sma_fast_str = f"{sma_fast:.{decimals}f}"
        else: sma_fast_str = str(sma_fast)
        if isinstance(sma_slow, float): sma_slow_str = f"{sma_slow:.{decimals}f}"
        else: sma_slow_str = str(sma_slow)
        if isinstance(sma_trend, float): sma_trend_str = f"{sma_trend:.{decimals}f}"
        else: sma_trend_str = str(sma_trend)

        details += f"\n- SMA {SMA_FAST}/{SMA_SLOW}: <code>{sma_fast_str}</code> / <code>{sma_slow_str}</code>"
        details += f"\n- Filtr Trendu (SMA {SMA_TREND_FILTER}): <code>{sma_trend_str}</code>"
        
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
        f"💰 <b>WEJŚCIE:</b> <b>{price:.{decimals}f}</b>\n" 
        # 2. TAKE PROFIT (bold) + WYNIK PIPS
        f"🎯 <b>TAKE PROFIT (R:R {TP_RATIO}):</b> <b>{tp_text}</b> ({reward_pips})\n" 
        # 3. STOP LOSS (bold) + RYZYKO PIPS
        f"🛑 <b>STOP LOSS:</b> <b>{sl_text}</b> ({sl_basis} Poprz. Świecy, {risk_pips})\n" 
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
    SMA_FAST_VAL = globals().get('SMA_FAST', 5)
    SMA_SLOW_VAL = globals().get('SMA_SLOW', 12)
    SMA_TREND_FILTER_VAL = globals().get('SMA_TREND_FILTER', 50) # 🚨 NOWA WARTOŚĆ
    RSI_PERIOD_VAL = globals().get('RSI_PERIOD', 9)
    
    MACD_FAST_VAL = globals().get('MACD_FAST', 7)
    MACD_SLOW_VAL = globals().get('MACD_SLOW', 14)
    MACD_SIGNAL_VAL = globals().get('MACD_SIGNAL', 5)

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
        data['SL_Low'] = data['Low'].shift(1) # Zmiana nazwy dla spójności
        data['SL_High'] = data['High'].shift(1) # Zmiana nazwy dla spójności
        
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

    # Dodano SL_Low/SL_High do kolumn do czyszczenia NaN, aby uniknąć błędów
    kolumny_do_czyszczenia_NaN = ['Close', 'SMA_Slow', 'RSI', macd_name, 'SMA_Trend', 'SL_Low', 'SL_High'] 
    
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
    price = ostatni_wiersz['Close'].item()
    
    # 3. FILTRY
    
    # Filtr Trendu (SMA 50)
    trend_filter_buy = price > ostatni_wiersz['SMA_Trend'].item()
    trend_filter_sell = price < ostatni_wiersz['SMA_Trend'].item()
    
    # Filtr Konfluencji MACD (czy MACD jest powyżej/poniżej linii sygnału)
    macd_conf_buy = ostatni_wiersz['MACD_Direction_Buy'].item() 
    macd_conf_sell = ostatni_wiersz['MACD_Direction_Sell'].item() 
    
    # 🚨 NOWE FILTRY BEZPIECZEŃSTWA SL 🚨
    sl_low = ostatni_wiersz['SL_Low'].item()
    sl_high = ostatni_wiersz['SL_High'].item()
    
    # Weryfikacja SL dla BUY: SL (Low) musi być NIŻSZY niż cena wejścia, a różnica musi być > MIN_RISK
    sl_ok_buy = (sl_low < price) and (abs(price - sl_low) >= MIN_RISK)
    
    # Weryfikacja SL dla SELL: SL (High) musi być WYŻSZY niż cena wejścia, a różnica musi być > MIN_RISK
    sl_ok_sell = (sl_high > price) and (abs(price - sl_high) >= MIN_RISK)
    
    # =======================================================
    
    # 4. SPRAWDZENIE SYGNAŁÓW Z NOWYMI WARUNKAMI

    # SPRAWDZENIE SMA Crossover (Wymaga Trendu, Konfluencji MACD i POPRAWNEGO SL)
    try:
        # Zmieniona nazwa strategii na SMA Crossover (Filtrowany)
        if ostatni_wiersz['SMA_Buy'].item() and trend_filter_buy and macd_conf_buy and sl_ok_buy:
            generuj_alert(ostatni_wiersz, symbol, interwal, "SMA Crossover (Filtrowany)", "BUY", sl_low)
            
        if ostatni_wiersz['SMA_Sell'].item() and trend_filter_sell and macd_conf_sell and sl_ok_sell: 
            generuj_alert(ostatni_wiersz, symbol, interwal, "SMA Crossover (Filtrowany)", "SELL", sl_high)
    except KeyError:
        pass 
        
    # SPRAWDZENIE RSI (Wymaga Trendu, Konfluencji MACD i POPRAWNEGO SL)
    try:
        # Zmieniona nazwa strategii na RSI Reversal (Filtrowany)
        if ostatni_wiersz['RSI_Buy'].item() and trend_filter_buy and macd_conf_buy and sl_ok_buy: 
            generuj_alert(ostatni_wiersz, symbol, interwal, f"RSI Reversal (Filtrowany)", "BUY", sl_low)
            
        if ostatni_wiersz['RSI_Sell'].item() and trend_filter_sell and macd_conf_sell and sl_ok_sell:
            generuj_alert(ostatni_wiersz, symbol, interwal, f"RSI Reversal (Filtrowany)", "SELL", sl_high)
    except KeyError:
        pass 
        
    # SPRAWDZENIE MACD Crossover (Wymaga Filtracji Trendu i POPRAWNEGO SL)
    # MACD Crossover wymaga tylko filtra trendu i poprawnego SL (MACD Conf jest w tej strategii tylko "wsparciem")
    try:
        if ostatni_wiersz['MACD_Buy'].item() and trend_filter_buy and sl_ok_buy:
            generuj_alert(ostatni_wiersz, symbol, interwal, "MACD Crossover", "BUY", sl_low)
            
        if ostatni_wiersz['MACD_Sell'].item() and trend_filter_sell and sl_ok_sell:
            generuj_alert(ostatni_wiersz, symbol, interwal, "MACD Crossover", "SELL", sl_high)
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
            "       👁️      \n"
            "👑 **SO-ZE** 👑\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "✅ **BOT STARTUJE!** Usługa Render aktywna 24/7.\n"
            f"🛠️ **STRATEGIA:** SCALPING (SMA {SMA_FAST}/{SMA_SLOW}, RSI {RSI_PERIOD})\n"
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

# UWAGA: Usunięto: if __name__ == "__main__":, ponieważ nie jest potrzebne na Renderze
