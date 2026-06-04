from html.parser import HTMLParser

class LinkedInParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_post = False
        self.tags = []
        
    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))
        
    def handle_endtag(self, tag):
        if self.tags:
            self.tags.pop()
            
    def handle_data(self, data):
        if "Synechron India" in data:
            print("Found post content!")
            for t in self.tags[-20:]:
                print(t)

with open("debug_search.html", "r", encoding="utf-8") as f:
    parser = LinkedInParser()
    parser.feed(f.read())
