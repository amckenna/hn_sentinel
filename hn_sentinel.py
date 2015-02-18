import requests, json, sys, time, sqlite3, time, datetime, threading, Queue
from operator import itemgetter
from flask import Flask, request, g, make_response, render_template
app = Flask(__name__)

DATABASE = "database.db"

# TODO: add functionality for daily, weekly, monthly, and yearly top posts
# TODO: setup cron job to update every hour on the 30 minute mark

#
# database helper methods
#

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
    return db

def query_db(query, args=(), one=False):
    db = get_db()
    cur = db.execute(query, args)
    db.commit()
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv

def insert_record(item_dict):
	q = query_db("INSERT OR REPLACE INTO stories (story_id, time_posted, score, title, url, by) VALUES (?,?,?,?,?,?)", \
				(item_dict["item_id"], item_dict["time"], item_dict["score"], item_dict["title"], item_dict["url"], item_dict["by"]))
	if q:
		return True
	else:
		return False

# returns array of (score, details) tuples
def get_top_stories(start_date,end_date):
	q = query_db("SELECT score, time_posted, title, url, story_id FROM stories WHERE time_posted > ? AND time_posted < ?", (start_date,end_date))
	results = []
	for e in q:
		results.append((e[0],[e[1],e[2],e[3],e[4]]))
	return results

# 
# API helper methods
# 

# returns json
def make_request(url):
	try:
		return requests.get(url, timeout=5.0).json()
		return j
	except:
		return ""

# returns json
def get_item(id, q):
	endpoint = "https://hacker-news.firebaseio.com/v0/item/%s.json" % id
	q.put(make_request(endpoint))

# returns dict
def parse_item_details(item_json):
	item_id = item_json["id"]
	title = item_json["title"]
	url = item_json["url"]
	post_type = item_json["type"]
	score = item_json["score"]
	by = item_json["by"]
	time = item_json["time"]
	return {'item_id': item_id, 'title': title, 'url': url, 'post_type': post_type, 'score': score, 'by': by, 'time': time}

# returns an array of tuples with story details (score,[date_posted, title, link, id, time_since_posted])
def format_for_rendering(top_stories,posts_to_return=30):
	top_stories.sort(key=itemgetter(0), reverse=True)
	top_stories = top_stories[0:posts_to_return]
	for story in top_stories:
		epoch_time = story[1][0]
		story[1][0] = format_from_epoch_to_date_time_string(epoch_time)
		story[1].append("%sh %sm ago" % calculate_time_from_now(epoch_time))
	return top_stories

# returns string
def format_from_epoch_to_date_time_string(epoch_time):
	return time.strftime('%Y-%m-%d %H:%M', time.localtime(float(epoch_time)))

# returns string
def format_from_epoch_to_date_time_string_short(epoch_time):
	return time.strftime('%Y-%m-%d', time.localtime(float(epoch_time)))

# returs string
def format_from_date_time_to_string_short(date_time):
	return date_time.strftime('%Y-%m-%d')

# returs string
def format_from_date_time_to_date_time_string(date_time):
	return date_time.strftime('%Y-%m-%d %H:%M')

# returns int
def format_from_date_time_to_epoch(date_time):
	return int(time.mktime(date_time.timetuple()))

# returns string
def calculate_time_from_now(epoch_time):
	t = time.time()
	return int((t - epoch_time)//3600), int(((t - epoch_time)//60)%60)

# returns datetime
def calculate_last_midnight_datetime(date_time):
	return datetime.datetime.combine(date_time, datetime.time.min)

# returns int
def calculate_last_midnight_epoch(epoch_time):
	return int(time.mktime(datetime.datetime.combine(datetime.datetime.fromtimestamp(epoch_time), datetime.time.min).timetuple()))

# returns int
def calculate_next_midnight_epoch(epoch_time):
	return int(time.mktime(datetime.datetime.combine(datetime.datetime.fromtimestamp(epoch_time), datetime.time.max).timetuple()))

#
# Flask specific methods
#

# remove for production
@app.route('/i')
def init_db():
	q = query_db("CREATE TABLE stories (story_id INTEGER PRIMARY KEY, time_posted INTEGER, score INTEGER, title VARCHAR, url VARCHAR, by VARCHAR)", [], one=True)
	return "db created"

# updates the story database
@app.route("/u")
def update_top_stories():
	top_items_endpoint = "https://hacker-news.firebaseio.com/v0/topstories.json"
	top_items = make_request(top_items_endpoint)
	top_stories = []
	json_blobs = Queue.Queue()
	threads = []

	for item_id in top_items:
		t = threading.Thread(target=get_item,args=(item_id,json_blobs))
		threads.append(t)
		t.start()

	for thread in threads:
		thread.join()

	json_blobs.put("END")

	for json_blob in [i for i in iter(json_blobs.get, "END")]:
		if json_blob != "" and json_blob["type"] == "story" and "url" in json_blob: 
			if json_blob["url"] != "":
				parsed_item = parse_item_details(json_blob)
				top_stories.append((parsed_item["score"],parsed_item))
				insert_record(parsed_item)

	return "updated"

@app.route("/date/<string:date>")
def past_stories(date=0,home=False):
	if date != 0:
		if home:
			today_datetime = date
		else:
			today_datetime = datetime.datetime.strptime(date,"%Y-%m-%d")
		today_epoch = format_from_date_time_to_epoch(today_datetime)
		tomorrow_epoch = calculate_next_midnight_epoch(format_from_date_time_to_epoch(today_datetime))
		today = format_from_epoch_to_date_time_string_short(today_epoch)
		day_before = format_from_date_time_to_string_short(today_datetime - datetime.timedelta(days=1))
		day_after = format_from_date_time_to_string_short(today_datetime + datetime.timedelta(days=1))
		top_stories = get_top_stories(today_epoch, tomorrow_epoch)
		top_stories = format_for_rendering(top_stories,50)
		if home or format_from_date_time_to_string_short(today_datetime) == format_from_date_time_to_string_short(datetime.date.today()):
			response = make_response(render_template("stories.html",top_stories=top_stories,day_before=day_before,today=today))
		else:
			response = make_response(render_template("stories.html",top_stories=top_stories,day_before=day_before,today=today,day_after=day_after))
		return response
	else:
		return "error"

# the main page
@app.route("/")
def index():
	return past_stories(datetime.date.today(),True)


if __name__ == "__main__":
	app.run(debug=True)








