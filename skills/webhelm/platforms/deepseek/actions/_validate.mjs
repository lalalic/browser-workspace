export default async function validate({ helpers: h, log = console.log }) {
  const result = await h.js(
    `(()=>{const c=document.querySelector('textarea[placeholder="Message DeepSeek"]'),u=document.querySelector('input[type=file]');return{url:location.href,ready:location.hostname==='chat.deepseek.com'&&!!c&&!c.disabled&&!!u,accepts_images:!!u&&/\\.(png|jpg|jpeg)(,|$)/i.test(u.accept),accepted_image_extensions:u?u.accept.split(',').filter(x=>/^\\.(png|jpe?g|webp|gif|bmp|tiff?|avif)$/i.test(x)):[]}})()`,
  );
  log(JSON.stringify(result));
  return result;
}
