new_tab("https://www.capcut.com/editor")
wait_for_load()

info = page_info()
print(f"Opened CapCut editor: {info['url']}")
print("No media was imported and no project was edited or exported.")
print(snapshot())