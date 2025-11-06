import yfinance as yf
import pandas as pd
import time
import pandas_ta as ta
from telegram import Bot
import asyncio
import requests
import os 
from telegram.error import NetworkError

# ==================== USTAWIENIA TELEGRAMA (CZYTANE Z ENV) ====================
# WAŻNE: Na Render.com używaj Zmiennych Środowiskowych!
TELEGRAM_BOT_TOKEN = "8346426967:AAFboh8UQzHZfSRFW4qvXMGG2fzM0-DsO80" # TOKEN W CUDZYSŁOWACH!
TELEGRAM_CHAT_ID = "6703750254"
# =============================================================================

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
TP_RATIO = 2.0                   # Współczynnik Risk:Reward dla TP (R:R 1:2)
wait_time = 60 # 60 sekund = 1 minuta
# ------------------------------------------------------------

# ----------------- USTAWIENIA PARAMETRÓW WSZKAŹNIKÓW -----------------
SMA_FAST = 10
SMA_SLOW = 20
SMA_TREND_FILTER = 100 # Filtr trendu (długoterminowa średnia)
RSI_PERIOD = 14 
RSI_LOW_LEVEL = 30 
RSI_HIGH_LEVEL = 70 
# Parametry MACD
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
# --------------------------------------------------------------------

# ==================== FUNKCJA POMOCNICZA DO OBLICZANIA PIPSÓW ====================
def oblicz_pipsy(symbol, roznica):
    """
    Oblicza różnicę cenową wyrażoną w pipsach.
    Standardowa pips to 0.0001 dla większości par i 0.01 dla par z JPY.
    """
    if "JPY" in symbol:
        # Pips dla par JPY jest na drugim miejscu po przecinku (0.01)
        pips_val = 0.01
    elif "BTC" in symbol or "GC=F" in symbol or "SI=F" in symbol:
        # Dla towarów i krypto używamy po prostu standardowych jednostek
        # i nie nazywamy ich pipsami, aby uniknąć pomyłek, 
        # ale wyświetlamy 2 miejsca po przecinku.
        return f"{abs(roznica):.2f} (Jednostek)"
    else:
        # Pips dla większości par Forex jest na czwartym miejscu po przecinku (0.0001)
        pips_val = 0.0001
        
    pips = abs(roznica) / pips_val
    return f"{pips:.1f} (Pipsów)"

# =================================================================================


async def wyslij_alert(alert_text):
    """Wysyła alert za pomocą Telegrama asynchronicznie."""
    try:
        # Poprawka: Użycie Bot z tokenem.
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID, 
            text=alert_text, 
            parse_mode='HTML'
        )
        print("✅ ALERT WYSŁANY DO TELEGRAMA: " + alert_text.split('\n')[0])
    except NetworkError as e:
        print(f"❌ BŁĄD SIECI TELEGRAMU: {e}. Sprawdź token i połączenie.")
    except Exception as e:
        print(f"❌ BŁĄD WYSYŁANIA TELEGRAMU: {e}")

async def generuj_alert(wiersz, symbol, interwal, strategia, kierunek):
    """Formatuje i wysyła ładniejszy i bardziej szczegółowy alert sygnału."""
    
    # Krok 1: Bezpieczne pobranie kluczowych danych
    # Używamy .iloc[-1] jeśli 'wiersz' jest DataFramem z jednym wierszem
    try:
        price = wiersz['Close'].item()
    except:
        # Jeśli dostaniemy serię zamiast DataFrame z itemem
        price = wiersz['Close'] 

    # POBIERANIE SL/TP
    sl_low_item = wiersz.get('RSI_SL_Low', pd.NA) 
    sl_high_item = wiersz.get('RSI_SL_High', pd.NA)

    # Upewnienie się, że pobieramy pojedynczą wartość
    try:
        sl_low_val = sl_low_item.item() if sl_low_item is not pd.NA and isinstance(sl_low_item, pd.Series) else sl_low_item
    except:
        sl_low_val = sl_low_item
    
    try:
        sl_high_val = sl_high_item.item() if sl_high_item is not pd.NA and isinstance(sl_high_item, pd.Series) else sl_high_item
    except:
        sl_high_val = sl_high_item


    sl_val = None
    
    if kierunek == "BUY":
        emoji = "🟢"
        sl_val = sl_low_val
    else: # SELL
        emoji = "🔴"
        sl_val = sl_high_val

    # Krok 2: Obliczanie SL i TP
    sl_text = "N/A"
    tp_text = "N/A"
    
    # NOWE ZMIENNE DLA WYLICZENIA PIPSÓW
    pips_risk = "N/A"
    pips_reward = "N/A"

    if sl_val is not None and pd.notna(sl_val):
        try:
            # Używamy price i sl_val jako floaty
            sl_text = f"{sl_val:.5f}"
            price_f = float(price)
            sl_val_f = float(sl_val)
            
            # Obliczenie ryzyka/nagrody
            if kierunek == "BUY":
                risk_roznica = price_f - sl_val_f
                tp_val = price_f + risk_roznica * TP_RATIO
                reward_roznica = tp_val - price_f
            else: # SELL
                risk_roznica = sl_val_f - price_f
                tp_val = price_f - risk_roznica * TP_RATIO
                reward_roznica = price_f - tp_val

            # OBLICZANIE PIPSÓW
            pips_risk = oblicz_pipsy(symbol, risk_roznica)
            pips_reward = oblicz_pipsy(symbol, reward_roznica)
                
            tp_text = f"{tp_val:.5f}"
        except Exception as e:
            print(f"Błąd obliczania SL/TP: {e}")
            sl_text = "Błąd SL"
            tp_text = "Błąd TP"

    # Krok 3: Szczegóły wskaźników (dodanie danych kontekstowych)
    details = f"\n\n⚙️ <b>Szczegóły Wskaźników ({strategia})</b>:"
    
    # Bezpieczne pobieranie wartości wskaźników
    def get_indicator_val(col_name):
        val = wiersz.get(col_name, pd.NA)
        try:
            return val.item() if isinstance(val, pd.Series) else val
        except:
            return val

    if "SMA" in strategia or "Cnf" in strategia:
        sma_fast = get_indicator_val('SMA_Fast')
        sma_slow = get_indicator_val('SMA_Slow')
        sma_trend = get_indicator_val('SMA_Trend')
        
        sma_fast_text = f"{sma_fast:.5f}" if pd.notna(sma_fast) else "N/A"
        sma_slow_text = f"{sma_slow:.5f}" if pd.notna(sma_slow) else "N/A"
        sma_trend_text = f"{sma_trend:.5f}" if pd.notna(sma_trend) else "N/A"

        details += f"\n- SMA {SMA_FAST}/{SMA_SLOW}: <code>{sma_fast_text}</code> / <code>{sma_slow_text}</code>"
        details += f"\n- Filtr Trendu (SMA {SMA_TREND_FILTER}): <code>{sma_trend_text}</code>"
        
    if "RSI" in strategia:
        rsi_val = get_indicator_val('RSI')
        rsi_text = f"{rsi_val:.2f}" if pd.notna(rsi_val) else "N/A"
        details += f"\n- RSI: <code>{rsi_text}</code> (Buy/Sell: {RSI_LOW_LEVEL}/{RSI_HIGH_LEVEL})"

    # MACD 
    if "MACD" in strategia or "Cnf" in strategia: 
        macd_val = get_indicator_val('MACD_Value')
        signal_val = get_indicator_val('MACDS_Value')
        
        macd_text = f"{macd_val:.5f}" if pd.notna(macd_val) else "N/A"
        signal_text = f"{signal_val:.5f}" if pd.notna(signal_val) else "N/A"
        
        details += f"\n- MACD/Signal: <code>{macd_text}</code> / <code>{signal_text}</code>"
        
    # Krok 4: Składanie gotowej wiadomości
    alert_text = (
        f"{emoji} <b>NOWY SYGNAŁ {kierunek}</b> ({strategia}) {emoji}\n"
        f"————————————————————\n"
        f"📊 <b>PARA:</b> <code>{symbol} / {interwal}</code>\n"
        f"\n"
        # 1. WEJŚCIE (bold)
        f"💰 <b>WEJŚCIE:</b> <b>{price:.5f}</b>\n" 
        # 2. TAKE PROFIT (bold) + Pipsy
        f"🎯 <b>TAKE PROFIT (R:R {TP_RATIO}):</b> <b>{tp_text}</b> (<code>{pips_reward}</code>)\n" 
        # 3. STOP LOSS (bold) + Pipsy
        f"🛑 <b>STOP LOSS:</b> <b>{sl_text}</b> (<code>{pips_risk}</code>)\n" 
        f"    {'Low' if kierunek == 'BUY' else 'High'} Poprz. Świecy\n"
        f"{details}"
    )

    # Wysłanie alertu
    await wyslij_alert(alert_text)


def pobierz_dane(symbol, interwal):
    """
    Pobiera historyczne dane OHLC z yfinance.
    Dostosowuje 'period' w zależności od 'interval', aby uniknąć limitów Yahoo Finance (60 dni dla interwałów < 1h).
    """
    
    # Logika dostosowania okresu:
    # 5m i 15m (krótkie interwały) muszą mieć period <= 60d
    # 1h i dłuższe mogą mieć period do 730d (2 lata)
    if interwal in ["5m", "15m", "30m"]:
        # Ustawiamy period na 59 dni, aby być bezpiecznym poniżej 60 dni
        period_val = "59d"
    else:
        # Dla 1h i dłuższych, używamy 120 dni, aby obliczyć SMA 100
        period_val = "120d" 
        
    print(f"DEBUG: YF Pobieram dane dla {symbol} {interwal} z period={period_val}")

    try:
        data = yf.download(symbol, interval=interwal, period=period_val, progress=False) 
        
        if data.empty:
            print(f"❌ POBIERANIE DANYCH PUSTE dla {symbol} ({interwal}).")
            return pd.DataFrame()  
        
        print(f"DEBUG: YF Pobrana długość dla {symbol} {interwal}: {len(data)}")    
        return data
        
    except Exception as e:
        # Ten błąd powinien zostać teraz obsłużony, bo dostosowujemy period
        print(f"❌ BŁĄD POBIERANIA DANYCH dla {symbol} ({interwal}): {e}")
        return pd.DataFrame()

def oblicz_wskaźniki_dodatkowe(data):
    """Oblicza wskaźniki za pomocą biblioteki pandas_ta, z gwarantowaną normalizacją kolumn."""
    
    data = data.copy()
    
    # --- Pobieranie wartości globalnych ---
    SMA_FAST_VAL = globals().get('SMA_FAST', 10)
    SMA_SLOW_VAL = globals().get('SMA_SLOW', 20)
    SMA_TREND_FILTER_VAL = globals().get('SMA_TREND_FILTER', 100)
    RSI_PERIOD_VAL = globals().get('RSI_PERIOD', 14)
    MACD_FAST_VAL = globals().get('MACD_FAST', 12)
    MACD_SLOW_VAL = globals().get('MACD_SLOW', 26)
    MACD_SIGNAL_VAL = globals().get('MACD_SIGNAL', 9)

    try:
        # 1. NORMALIZACJA KOLUMN
        # Używamy ujednoliconego nazewnictwa kolumn (Close, High, Low)
        # To jest krytyczne, gdy yfinance zwraca (Symbol, Column) krotki lub tylko nazwy
        new_columns = [str(col[0]).title() if isinstance(col, tuple) else str(col).title() for col in data.columns]
        data.columns = new_columns
        
        if 'Close' not in data.columns:
            if 'Adj Close' in data.columns: data['Close'] = data['Adj Close']
            else: raise ValueError("Kolumna 'Close' jest pusta lub jej brakuje po ujednoliceniu.")

        # 2. Konwersja typów (zabezpieczenie)
        data['Close'] = data.get('Close', pd.Series(dtype='float64')).astype('float64')
        data['Low'] = data.get('Low', pd.Series(dtype='float64')).astype('float64')
        data['High'] = data.get('High', pd.Series(dtype='float64')).astype('float64')

        if data['Close'].empty or data['Close'].isnull().all():
            raise ValueError(f"Kolumna 'Close' jest pusta po normalizacji. Dostępne kolumny: {data.columns.tolist()}")

        # 3. SMA 
        data['SMA_Fast'] = ta.sma(data['Close'], length=SMA_FAST_VAL)
        data['SMA_Slow'] = ta.sma(data['Close'], length=SMA_SLOW_VAL)
        data['SMA_Trend'] = ta.sma(data['Close'], length=SMA_TREND_FILTER_VAL)
        
        data['SMA_Buy'] = (data['SMA_Fast'] > data['SMA_Slow']) & (data['SMA_Fast'].shift(1) <= data['SMA_Slow'].shift(1))
        data['SMA_Sell'] = (data['SMA_Fast'] < data['SMA_Slow']) & (data['SMA_Fast'].shift(1) >= data['SMA_Slow'].shift(1))
        
        # 4. RSI 
        data['RSI'] = ta.rsi(data['Close'], length=RSI_PERIOD_VAL)
        
        RSI_LOW_LEVEL_VAL = globals().get('RSI_LOW_LEVEL', 30)
        RSI_HIGH_LEVEL_VAL = globals().get('RSI_HIGH_LEVEL', 70)
        data['RSI_Buy'] = (data['RSI'].shift(1) < RSI_LOW_LEVEL_VAL) & (data['RSI'] >= RSI_LOW_LEVEL_VAL)
        data['RSI_Sell'] = (data['RSI'].shift(1) > RSI_HIGH_LEVEL_VAL) & (data['RSI'] <= RSI_HIGH_LEVEL_VAL)

        # 5. MACD 
        # Używamy pandas_ta dla MACD, które dodaje kolumny z sygnaturą
        data.ta.macd(fast=MACD_FAST_VAL, slow=MACD_SLOW_VAL, signal=MACD_SIGNAL_VAL, append=True)
        
        macd_signature = f'_{MACD_FAST_VAL}_{MACD_SLOW_VAL}_{MACD_SIGNAL_VAL}'
        
        # Znajdowanie poprawnych nazw kolumn MACD
        found_macd_name = next((col for col in data.columns if macd_signature in col and col.lower().startswith('macd_') and 'h_' not in col.lower()), None)
        found_signal_name = next((col for col in data.columns if macd_signature in col and col.lower().startswith('macds_')), None)
        
        if found_macd_name is None or found_signal_name is None:
            # Próba znalezienia bez sygnatury (dla starszych wersji pandas_ta lub innych przypadków)
            found_macd_name = next((col for col in data.columns if col.lower().startswith('macd_') and 'h_' not in col.lower()), None)
            found_signal_name = next((col for col in data.columns if col.lower().startswith('macds_')), None)
            
            if found_macd_name is None or found_signal_name is None:
                # W ostateczności używamy domyślnych nazw, jeśli są obecne
                if 'MACD' in data.columns and 'MACDS' in data.columns:
                    found_macd_name = 'MACD'
                    found_signal_name = 'MACDS'
                else:
                    raise ValueError(f"Kolumny MACD/MACDS nie zostały utworzone poprawnie. Dostępne kolumny: {data.columns.tolist()}")

        data['MACD_Value'] = data[found_macd_name]
        data['MACDS_Value'] = data[found_signal_name]
        
        # Logika MACD Crossover
        data['MACD_Buy'] = (data['MACD_Value'] > data['MACDS_Value']) & (data['MACD_Value'].shift(1) <= data['MACDS_Value'].shift(1))
        data['MACD_Sell'] = (data['MACD_Value'] < data['MACDS_Value']) & (data['MACD_Value'].shift(1) >= data['MACDS_Value'].shift(1))
        
        # MACD KIERUNEK (Używany jako filtr konfluencji)
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
        
        print(f"DEBUG: ROZMIAR KOŃCOWY (PRZED RETURN): {len(data)}")
        
        return data
        
    except Exception as e:
        print("🛑 BŁĄD W OBLICZANIU WSKAŹNIKÓW - SMA/RSI/MACD!")
        print(f"PEŁNY BŁĄD: {e}") 
        return pd.DataFrame()

async def sprawdz_wszystkie_strategie(dane_ze_strategia, symbol, interwal):
    """Iteruje przez wszystkie sygnały w ostatniej świecy z uwzględnieniem filtracji."""
    
    if dane_ze_strategia.empty:
        return
        
    macd_name = 'MACD_Value'

    kolumny_do_czyszczenia_NaN = ['Close', 'SMA_Slow', 'RSI', macd_name, 'SMA_Trend', 'Low', 'High', 'RSI_SL_Low', 'RSI_SL_High'] 
    
    try:
        # Zabezpieczenie przed brakującymi kolumnami
        for col in kolumny_do_czyszczenia_NaN:
            if col not in dane_ze_strategia.columns: 
                print(f"OSTRZEŻENIE: Brak kolumny {col} w danych dla {symbol} {interwal}.")
                return
        
        dane_czyste = dane_ze_strategia.dropna(subset=kolumny_do_czyszczenia_NaN).copy()
    except KeyError as e:
        print(f"🛑 BŁĄD DANYCH: Nie można znaleźć wszystkich kolumn wskaźników w DF dla {symbol} {interwal}. Brak klucza: {e}")
        return
    
    
    if dane_czyste.empty or len(dane_czyste) < 2:
        print(f"OSTRZEŻENIE: Brak wystarczającej ilości danych do obliczenia wskaźników dla {symbol} {interwal}.")
        return

    # Krok 2: POBRANIE OSTATNIEGO WIERSZA DANYCH
    ostatni_wiersz = dane_czyste.iloc[-1]
    
    # 3. FILTRY
    
    # Filtr Trendu (SMA 100)
    trend_filter_buy = ostatni_wiersz['Close'] > ostatni_wiersz['SMA_Trend']
    trend_filter_sell = ostatni_wiersz['Close'] < ostatni_wiersz['SMA_Trend']
    
    # Filtr Konfluencji MACD (czy MACD jest powyżej/poniżej linii sygnału)
    macd_conf_buy = ostatni_wiersz['MACD_Direction_Buy'] 
    macd_conf_sell = ostatni_wiersz['MACD_Direction_Sell'] 

    
    # 4. SPRAWDZENIE SYGNAŁÓW Z NOWYMI WARUNKAMI

    # SPRAWDZENIE SMA Crossover (Wymaga Trendu i Konfluencji MACD)
    try:
        if ostatni_wiersz['SMA_Buy'] and trend_filter_buy and macd_conf_buy:
            # Przekazujemy ostatni wiersz jako Series, żeby nie używać .item()
            await generuj_alert(ostatni_wiersz, symbol, interwal, "SMA + MACD Cnf", "BUY")
            
        if ostatni_wiersz['SMA_Sell'] and trend_filter_sell and macd_conf_sell: 
            await generuj_alert(ostatni_wiersz, symbol, interwal, "SMA + MACD Cnf", "SELL")
    except KeyError:
        pass 
        
    # SPRAWDZENIE RSI (Wymaga Trendu i Konfluencji MACD)
    try:
        if ostatni_wiersz['RSI_Buy'] and trend_filter_buy and macd_conf_buy: 
            await generuj_alert(ostatni_wiersz, symbol, interwal, f"RSI + MACD Cnf", "BUY")
            
        if ostatni_wiersz['RSI_Sell'] and trend_filter_sell and macd_conf_sell:
            await generuj_alert(ostatni_wiersz, symbol, interwal, f"RSI + MACD Cnf", "SELL")
    except KeyError:
        pass 
        
    # SPRAWDZENIE MACD Crossover (Wymaga Filtracji Trendu)
    try:
        if ostatni_wiersz['MACD_Buy'] and trend_filter_buy:
            await generuj_alert(ostatni_wiersz, symbol, interwal, "MACD Crossover (Filtrowany)", "BUY")
            
        if ostatni_wiersz['MACD_Sell'] and trend_filter_sell:
            await generuj_alert(ostatni_wiersz, symbol, interwal, "MACD Crossover (Filtrowany)", "SELL")
    except KeyError:
        pass
        
    return
    
# ==================== GŁÓWNA PĘTLA ASYNCHRONICZNA ====================

async def main_bot():
    """Główna, asynchroniczna funkcja uruchamiająca bota 24/7."""
    
    print(f">>> BOT ALERT ZACZYNA PRACĘ. Monitoring {len(SYMBOLS)} par na {len(FRAMES)} interwałach i 3 strategiach! <<<")
    
    # Wysyłamy wiadomość startową
    await wyslij_alert(f"✅ SO-ZE: POMYŚLNIE POŁĄCZONY Telegram! Zaczynam skanowanie Filtrowanych Sygnałów.")
    
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
                        # Używamy await, ponieważ sprawdz_wszystkie_strategie jest teraz async
                        await sprawdz_wszystkie_strategie(dane_ze_strategia, symbol, frame)
                        
                except Exception as e:
                    print(f"❌ Wystąpił nieoczekiwany błąd w pętli dla {symbol} ({frame}): {e}")
        
        # Używamy asyncio.sleep zamiast time.sleep w kodzie asynchronicznym
        await asyncio.sleep(wait_time)

if __name__ == "__main__":
    try:
        asyncio.run(main_bot())
    except KeyboardInterrupt:
        print("🤖 Bot został ręcznie zatrzymany.")
    except RuntimeError as e:
        if "cannot run" in str(e) or "already running" in str(e):
            print(f"Wykryto, że pętla zdarzeń już działa. Uruchamiam funkcję w tle. Pełny błąd: {e}")
            # W przypadku środowiska, gdzie pętla już istnieje (np. Jupyter), obsługa jest inna
            asyncio.create_task(main_bot())
        else:
            raise

