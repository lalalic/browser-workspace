import json
import time
from urllib.parse import urlsplit

CFG=json.load(open("__CFG_PATH__",encoding="utf-8"))

def wait(pred,label,timeout=30):
    deadline=time.time()+timeout
    while time.time()<deadline:
        value=pred()
        if value:return value
        time.sleep(.2)
    raise RuntimeError(f"{label} not observed")

def composer():
    return js("""(() => {
      const sels=['#prompt-textarea','[contenteditable="true"][data-composer-markdown]','[contenteditable="true"][data-lexical-editor="true"]','textarea'];
      for(const s of sels){const e=document.querySelector(s);if(!e)continue;const r=e.getBoundingClientRect();if(r.width&&r.height)return s;}
      return null;
    })()""")

def set_value(selector,text):
    ok=js(f"""(() => {{
      const e=document.querySelector({json.dumps(selector)});
      if(!e)return false;e.focus();
      if(e instanceof HTMLTextAreaElement || e instanceof HTMLInputElement){{
        const p=e instanceof HTMLTextAreaElement?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;
        Object.getOwnPropertyDescriptor(p,'value')?.set?.call(e,{json.dumps(text)});
      }}else{{
        const sel=window.getSelection(),r=document.createRange();r.selectNodeContents(e);sel.removeAllRanges();sel.addRange(r);
        document.execCommand('delete',false,null);document.execCommand('insertText',false,{json.dumps(text)});sel.removeAllRanges();
      }}
      e.dispatchEvent(new InputEvent('input',{{bubbles:true,inputType:'insertText',data:{json.dumps(text)}}}));
      return true;
    }})()""")
    if not ok: raise RuntimeError("bootstrap composer could not be filled")

target_id=new_tab("https://chatgpt.com/")
wait_for_load()
selector=wait(composer,"ChatGPT bootstrap composer",45)
set_value(selector,CFG["instructions"])
button=wait(lambda: js("""(() => {
  const b=document.querySelector('button[data-testid="send-button"],button[aria-label="Send prompt"],button[aria-label="Send"],form button[type="submit"]');
  if(!b||b.disabled||b.getAttribute('aria-disabled')==='true')return null;
  b.setAttribute('data-bw-platform-bootstrap-send','1');return '[data-bw-platform-bootstrap-send="1"]';
})()"""),"ChatGPT bootstrap send button",20)
if not js("""(() => {const b=document.querySelector('[data-bw-platform-bootstrap-send="1"]');if(!b)return false;b.click();return true;})()"""):
    raise RuntimeError("bootstrap send failed")
deadline=time.time()+90
thread_url=None
while time.time()<deadline:
    current=page_info().get("url","")
    if "/c/" in urlsplit(current).path and "local-chatgpt" not in current:
        thread_url=current.split("?",1)[0]
        break
    time.sleep(.25)
if not thread_url: raise RuntimeError("bootstrap thread durable URL not observed")
print(json.dumps({"status":"started","thread_url":thread_url,"target_id":target_id},ensure_ascii=False),flush=True)
