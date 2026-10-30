import json

result = js(r"""(() => {
  const composer = document.querySelector('textarea[placeholder="Message DeepSeek"]');
  const upload = document.querySelector('input[type="file"]');
  return {
    url: location.href,
    ready: location.hostname === 'chat.deepseek.com' && !!composer && !composer.disabled && !!upload,
    accepts_images: !!upload && /\\.(png|jpg|jpeg)(,|$)/i.test(upload.accept),
    accepted_image_extensions: upload ? upload.accept.split(',').filter(ext =>
      /^\.(png|jpe?g|webp|gif|bmp|tiff?|avif)$/i.test(ext)) : []
  };
})()""")
print(json.dumps(result), flush=True)