import asyncio, os, logging, hmac
import aiohttp
from aiohttp import web
SITE="https://www.onlinedoctranslator.com/ar/"
def button(text, action):
 return {"text":text,"callback_data":action}
def menu(action="start"):
 rows=[[{"text":"🌐 فتح موقع الترجمة","url":SITE}]]
 if action in {"start","home"}:
  rows += [[button("📄 خطوات ترجمة الملف","help")], [button("🩺 مراجعة الترجمة الطبية","review"),button("🛠 حل المشكلات","troubleshoot")], [button("🔒 الخصوصية","privacy"),button("ℹ️ كيف يعمل البوت؟","about")]]
 elif action=="help":
  rows += [[button("التالي: مراجعة النتيجة ←","review")]]
 else:
  rows += [[button("📄 خطوات الترجمة","help"),button("🩺 قائمة المراجعة","review")]]
 if action not in {"start","home"}: rows += [[button("🏠 القائمة الرئيسية","home")]]
 return {"inline_keyboard":rows}
WELCOME="مِداد الطبي 🩺\nدليلك لترجمة المستندات الإنجليزية إلى العربية.\n\nابدأ بخطوات الترجمة، ثم استخدم قائمة المراجعة الطبية بعد تنزيل النتيجة.\n\nالخدمة مجانية. رفع الملف وتنزيل ترجمته يتمان يدويًا في الموقع؛ البوت لا يترجم الملفات أو يفحص محتواها."
HELP="📄 ترجمة ملفك — خطوة بخطوة\n\n1. احفظ الملف على جهازك من Telegram.\n2. افتح موقع الترجمة بالزر أدناه.\n3. ارفع الملف وحدد الإنجليزية لغة المصدر والعربية لغة النتيجة، وفق الخيارات المعروضة في الموقع.\n4. انتظر انتهاء المعالجة ثم نزّل الملف المترجم.\n5. افتح الأصل والترجمة جنبًا إلى جنب واستخدم قائمة المراجعة.\n\nأرسل المستند للبوت للحصول على هذه الإرشادات مع اسمه؛ لن يُرفع إلى الموقع تلقائيًا."
REVIEW="🩺 قائمة مراجعة الترجمة الطبية\n\n□ تطابق الأرقام والكسور والنسب مع الأصل.\n□ صحة الجرعات والوحدات مثل mg وmL وتكرار الاستخدام.\n□ بقاء النفي والتحذيرات وموانع الاستعمال بمعناها الأصلي.\n□ صحة أسماء الأدوية والمصطلحات والاختصارات؛ ارجع للاسم الإنجليزي عند الالتباس.\n□ عدم سقوط فقرات أو صفوف جداول أو ملاحظات أسفل الصفحة.\n□ وضوح العربية وترتيب العناوين والجداول.\n\nهذه قائمة مساعدة للمراجعة اليدوية، وليست تدقيقًا آليًا. المعلومات المؤثرة في العلاج تحتاج مراجعة مختص قبل الاعتماد عليها."
TROUBLESHOOT="🛠 حل مشكلات شائعة\n\n• الموقع لم يقبل الملف: راجع الصيغ والحجم المسموحين فيه؛ حدوده مستقلة عن البوت.\n• نص الصفحات عبارة عن صور: قد تحتاج لاستخراج النص بالتعرف الضوئي (OCR) أولًا ثم تصحيح أخطائه.\n• التنسيق تغير: جرّب نسخة Word إن توفرت، وقارن الجداول والعناوين بالأصل.\n• الترجمة ناقصة: جرّب تقسيم الملف إلى أجزاء أصغر، مع حفظ ترتيبها.\n• البوت تأخر في الرد: قد تستغرق الاستضافة المجانية وقتًا للاستيقاظ؛ انتظر ثم أعد المحاولة."
PRIVACY="🔒 خصوصية الملفات\n\nالبوت يقرأ اسم المستند وحجمه من رسالة Telegram لعرض الإرشادات؛ لا ينزّل محتواه ولا يرسله للموقع. لا نسجل نص الرسائل أو أسماء الملفات في سجلات التطبيق.\n\nالرسائل تخضع لسياسة Telegram، والملفات التي ترفعها بنفسك تخضع لسياسة موقع الترجمة. أزل أسماء المرضى وأرقامهم وأي بيانات تعريفية قبل رفع المستندات."
ABOUT="ℹ️ كيف يعمل مِداد؟\n\nبوت إرشادي مستقل، غير تابع لموقع Online Doc Translator. يوفر خطوات الترجمة وقائمة مراجعة وحلولًا للمشكلات.\n\nلا ينفذ ترجمة أو تدقيقًا طبيًا تلقائيًا، ولا يستلم النتيجة من الموقع. لا باقات مدفوعة أو نجوم."
class Bot:
 def __init__(self, token): self.token=token
 async def api(self,method,**payload):
  async with self.http.post("https://api.telegram.org/bot"+self.token+"/"+method,json=payload) as r:
   result=await r.json()
   if not result.get("ok"): raise RuntimeError("Telegram request failed")
   return result["result"]
 async def handle(self,u):
  cb=u.get("callback_query");m=u.get("message") or {}
  if cb:
   await self.api("answerCallbackQuery",callback_query_id=cb["id"])
   m=cb.get("message") or {};action=cb.get("data","")
  else:
   raw=m.get("text") or ""
   action=raw.split(" ")[0].split("@")[0].lstrip("/")
  if m.get("chat",{}).get("type")!="private": return
  screens={"start":WELCOME,"home":WELCOME,"help":HELP,"review":REVIEW,"troubleshoot":TROUBLESHOOT,"privacy":PRIVACY,"terms":PRIVACY,"about":ABOUT}
  if m.get("document") and not cb:
   doc=m["document"]
   name=str(doc.get("file_name") or "مستند بدون اسم")[:180]
   size=doc.get("file_size")
   details=f"\nالحجم: {size/1024/1024:.2f} MB" if isinstance(size,(int,float)) and size>=0 else ""
   text=f"📄 مستندك: {name}{details}\n\nالبوت لا يعالج محتوى الملف تلقائيًا. احفظه على جهازك وارفعه بنفسك للموقع.\n\n"+HELP
   action="help"
  elif action in {"buy","shop","paysupport","balance"}:
   text="الخدمة مجانية. أُلغيت المدفوعات والباقات.\n\n"+WELCOME;action="home"
  elif action=="status": text=ABOUT;action="about"
  elif m.get("photo") and not cb:
   text="🖼 أرسلت صورة. لترجمة مستند مصوّر، راجع قسم حل المشكلات لاستخراج النص أولًا. لا يحلل البوت الصور.";action="troubleshoot"
  else:
   text=screens.get(action,"اختر ما تحتاجه من القائمة أدناه.\n\n"+WELCOME)
   if action not in screens: action="home"
  payload={"chat_id":m["chat"]["id"],"text":text,"reply_markup":menu(action)}
  if cb and m.get("message_id"):
   # Avoid Telegram's 'message is not modified' error on repeated taps.
   if m.get("text")==text and m.get("reply_markup")==payload["reply_markup"]: return
   await self.api("editMessageText",message_id=m["message_id"],**payload)
  else: await self.api("sendMessage",**payload)
 async def run(self):
  secret=os.environ['WEBHOOK_SECRET']
  if len(secret)<32: raise ValueError('Webhook secret too short')
  url=os.environ['RENDER_EXTERNAL_URL'].rstrip('/')
  if not url.startswith('https://'): raise ValueError('HTTPS required')
  app=web.Application(client_max_size=1024*1024)
  ready=False
  async def health(request): return web.json_response({'ok':ready,'mode':'free-guide'},status=200 if ready else 503)
  async def webhook(request):
   if not hmac.compare_digest(request.headers.get('X-Telegram-Bot-Api-Secret-Token',''),secret): raise web.HTTPUnauthorized()
   try: update=await request.json()
   except (ValueError,TypeError): raise web.HTTPBadRequest()
   if not isinstance(update,dict): raise web.HTTPBadRequest()
   try: await self.handle(update)
   except Exception as e:
    logging.warning('Webhook failed: %s',type(e).__name__)
    raise web.HTTPServiceUnavailable()
   return web.json_response({'ok':True})
  app.router.add_get('/',health);app.router.add_get('/health',health);app.router.add_post('/telegram',webhook)
  runner=web.AppRunner(app);await runner.setup()
  await web.TCPSite(runner,'0.0.0.0',int(os.getenv('PORT','8080'))).start()
  try:
   async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as self.http:
    await self.api('getMe')
    await self.api('setMyCommands',commands=[{'command':x,'description':y} for x,y in [('start','القائمة الرئيسية'),('help','خطوات ترجمة الملف'),('review','مراجعة الترجمة الطبية'),('troubleshoot','حل المشكلات'),('privacy','خصوصية الملفات'),('about','كيف يعمل البوت')]])
    await self.api('setMyDescription',description='مِداد الطبي: إرشاد مجاني لترجمة المستندات عبر Online Doc Translator. افتح الموقع وارفع الملف هناك. البوت لا يترجم الملفات تلقائيًا ولا يبيع خدمات.')
    await self.api('setWebhook',url=url+'/telegram',secret_token=secret,allowed_updates=['message','callback_query'],max_connections=5)
    ready=True
    await asyncio.Event().wait()
  finally: await runner.cleanup()
if __name__=='__main__': asyncio.run(Bot(os.environ['BOT_TOKEN']).run())
