from playwright.sync_api import sync_playwright
from PIL import Image
import os
import re
import requests

# --- 從環境變數安全讀取 Telegram 配置 ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def send_message_to_telegram(chat_id, bot_token, text):
    """傳送純文字錯誤訊息到 Telegram，方便除錯"""
    if not bot_token or not chat_id:
        print("未設定 Telegram Token 或 Chat ID，無法發送訊息。")
        return
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = {'chat_id': chat_id, 'text': text}
    try:
        requests.post(url, data=data)
    except Exception as e:
        print(f"發送錯誤訊息失敗: {e}")

def send_photo_to_telegram(chat_id, bot_token, image_path, caption=None):
    """將圖片發送到 Telegram 聊天。"""
    if not bot_token or not chat_id:
        print("未設定 Telegram Token 或 Chat ID，無法發送圖片。")
        return
        
    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    
    with open(image_path, 'rb') as photo_file:
        files = {'photo': (os.path.basename(image_path), photo_file, 'image/png')}
        data = {'chat_id': chat_id}
        if caption:
            data['caption'] = caption

        try:
            response = requests.post(url, data=data, files=files)
            response.raise_for_status()
            json_response = response.json()
            if json_response.get("ok"):
                print(f"圖片 '{os.path.basename(image_path)}' 已成功發送到 Telegram。")
            else:
                error_desc = json_response.get('description', '未知錯誤')
                print(f"發送圖片到 Telegram 失敗：{error_desc}")
                send_message_to_telegram(chat_id, bot_token, f"❌ 發送圖片失敗：{error_desc}")
        except requests.exceptions.RequestException as e:
            print(f"發送圖片到 Telegram 時發生網路錯誤：{e}")
            send_message_to_telegram(chat_id, bot_token, f"❌ 發送圖片網路錯誤：{e}")
        except Exception as e:
            print(f"發送圖片到 Telegram 時發生未知錯誤：{e}")

def capture_and_crop_specific_c_wiz_element_unified_dir(urls, element_index_to_capture, crop_width, crop_height, base_output_directory, viewport_width=1280, viewport_height=900):
    if not urls:
        print("未提供任何網址，請提供至少一個網址。")
        return

    # 確保統一的輸出目錄存在
    if not os.path.exists(base_output_directory):
        os.makedirs(base_output_directory)
        print(f"已創建統一輸出目錄：{base_output_directory}")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        
        for url_index, url in enumerate(urls):
            print(f"\n--- 正在處理網址 #{url_index + 1}: {url} ---")
            
            match = re.search(r'id=([^&]+)', url)
            app_id = match.group(1) if match else f"unknown_app_{url_index}"
            
            page = browser.new_page()
            page.set_viewport_size({"width": viewport_width, "height": viewport_height})

            try:
                print(f"正在開啟網頁: {url}")
                page.goto(url)
                page.wait_for_load_state('networkidle', timeout=30000) 

                c_wiz_elements = page.locator('c-wiz[jsrenderer]').all()

                if not c_wiz_elements:
                    error_msg = f"⚠️ 網址 {url} 上未找到任何帶有 'jsrenderer' 屬性的 <c-wiz> 元素。"
                    print(error_msg)
                    send_message_to_telegram(TELEGRAM_CHAT_ID, TELEGRAM_BOT_TOKEN, error_msg)
                    page.close()
                    continue

                if element_index_to_capture > len(c_wiz_elements) or element_index_to_capture <= 0:
                    error_msg = f"⚠️ 警告：網址 {url} ('{app_id}') 上的 <c-wiz> 元素數量 ({len(c_wiz_elements)}) 不足。無法截取第 {element_index_to_capture} 個元素。"
                    print(error_msg)
                    send_message_to_telegram(TELEGRAM_CHAT_ID, TELEGRAM_BOT_TOKEN, error_msg)
                    page.close()
                    continue

                target_element_locator = c_wiz_elements[element_index_to_capture - 1]
                
                try:
                    jsrenderer_value = target_element_locator.get_attribute("jsrenderer")
                    safe_jsrenderer_value = (jsrenderer_value or f"no_jsrenderer_{element_index_to_capture}") 
                    safe_jsrenderer_value = re.sub(r'[\\/:*?"<>|]', '_', safe_jsrenderer_value) 
                    
                    temp_full_screenshot_name = f"temp_{app_id}_element_{element_index_to_capture}_{safe_jsrenderer_value}.png"
                    temp_full_screenshot_path = os.path.join(base_output_directory, temp_full_screenshot_name)

                    final_cropped_image_name = f"{app_id}_element_{element_index_to_capture}_cropped_{crop_width}x{crop_height}.png"
                    final_cropped_image_path = os.path.join(base_output_directory, final_cropped_image_name)

                    print(f"正在截取網址 {url} 上第 {element_index_to_capture} 個元素...")
                    target_element_locator.wait_for(state="visible", timeout=5000) 
                    target_element_locator.screenshot(path=temp_full_screenshot_path)

                    # --- 執行裁剪 ---
                    try:
                        with Image.open(temp_full_screenshot_path) as img:
                            original_width, original_height = img.size
                            
                            right = min(crop_width, original_width)
                            bottom = min(crop_height, original_height)
                            
                            cropped_img = img.crop((0, 0, right, bottom))
                            cropped_img.save(final_cropped_image_path)
                            print(f"裁剪後的圖片已保存到：{final_cropped_image_path}")
                            
                            # --- 發送圖片到 Telegram ---
                            caption_text = f"來自 {app_id} (第 {element_index_to_capture} 個元素) 的裁剪圖片"
                            send_photo_to_telegram(TELEGRAM_CHAT_ID, TELEGRAM_BOT_TOKEN, final_cropped_image_path, caption=caption_text)

                    except Exception as crop_e:
                        error_msg = f"❌ 裁剪圖片 {app_id} 時發生錯誤：{crop_e}"
                        print(error_msg)
                        send_message_to_telegram(TELEGRAM_CHAT_ID, TELEGRAM_BOT_TOKEN, error_msg)
                    finally:
                        if os.path.exists(temp_full_screenshot_path):
                            os.remove(temp_full_screenshot_path)

                except Exception as element_e:
                    error_msg = f"❌ 截取或處理第 {element_index_to_capture} 個元素 (來自 {app_id}) 時發生錯誤：{element_e}"
                    print(error_msg)
                    send_message_to_telegram(TELEGRAM_CHAT_ID, TELEGRAM_BOT_TOKEN, error_msg)
            
            except Exception as e:
                error_msg = f"❌ 處理網址 {url} 時發生錯誤：{e}"
                print(error_msg)
                send_message_to_telegram(TELEGRAM_CHAT_ID, TELEGRAM_BOT_TOKEN, error_msg)
            finally:
                if 'page' in locals() and not page.is_closed():
                    page.close() 

        browser.close()
        print("\n--- 所有網址處理完畢 ---")

if __name__ == "__main__":
    target_urls = [
        "https://play.google.com/store/apps/details?id=io.gstfun.bc_game_app",
        "https://play.google.com/store/apps/details?id=shop.kubon"
    ]

    element_to_capture_index = 6
    desired_crop_width = 1280
    desired_crop_height = 355

    # 更改為相對路徑，適合 GitHub Actions 上的 Linux 環境
    output_base_directory = "./output_pics" 

    capture_and_crop_specific_c_wiz_element_unified_dir(
        target_urls,
        element_to_capture_index,
        desired_crop_width,
        desired_crop_height,
        base_output_directory=output_base_directory 
    )
