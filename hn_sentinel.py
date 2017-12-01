import requests, json, sys, time, sqlite3, time, datetime, calendar, threading, Queue
from dateutil.relativedelta import relativedelta
from operator import itemgetter
from flask import Flask, request, g, make_response, render_template, abort
app = Flask(__name__)

DATABASE = "database.db"

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

    q2 = query_db("INSERT OR REPLACE INTO comment_count (story_id, comment_count) VALUES (?,?)", \
                (item_dict["item_id"], item_dict["comments"]))
    if q and q2:
		return True
    else:
        return False

# returns array of (score, details) tuples
def get_top_stories(start_date,end_date):
	q = query_db("SELECT score, time_posted, title, url, story_id, comment_count FROM stories NATURAL LEFT OUTER JOIN comment_count WHERE time_posted > ? AND time_posted < ?", (start_date,end_date))
	results = []
	for e in q:
		results.append({'score':e[0],'time_posted':format_from_epoch_to_date_time_string(e[1]),'title':e[2],'url':e[3],'story_id':e[4],'comment_count':e[5],'time_since':'%sh %sm ago' % calculate_time_from_now(e[1])})
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
    comments = item_json["descendants"]
    return {'item_id': item_id, 'title': title, 'url': url, 'post_type': post_type, 'score': score, 'by': by, 'time': time, 'comments': comments}

def trim_stories(top_stories,posts_to_return=30):
	top_stories.sort(key=itemgetter('score'), reverse=True)
	top_stories = top_stories[0:posts_to_return]
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

# returns current day, week range, month range, and year range
def get_date_links():
	date = datetime.datetime.date(datetime.datetime.now())
	year = date.today().year
	month = date.today().month

	week_start 	= date - datetime.timedelta(days=date.weekday())
	week_end 	= week_start + datetime.timedelta(days=6)
	month_start = date.today().replace(day=1)
	month_end 	= datetime.date(year, month, calendar.monthrange(year, month)[1])
	year_start 	= datetime.date(date.today().year, 1, 1)
	year_end 	= datetime.date(date.today().year, 12, 31)

	day_link 	= format_from_date_time_to_string_short(datetime.datetime.now())
	week_link 	= "%s/%s" % (format_from_date_time_to_string_short(week_start),format_from_date_time_to_string_short(week_end))
	month_link 	= "%s/%s" % (format_from_date_time_to_string_short(month_start),format_from_date_time_to_string_short(month_end))
	year_link 	= "%s/%s" % (format_from_date_time_to_string_short(year_start),format_from_date_time_to_string_short(year_end))

	return day_link, week_link, month_link, year_link

#
# Flask specific methods
#

# remove for production
#@app.route('/i')
#def init_db():
#	q = query_db("CREATE TABLE stories (story_id INTEGER PRIMARY KEY, time_posted INTEGER, score INTEGER, title VARCHAR, url VARCHAR, by VARCHAR)", [], one=True)
#	return "db created"

@app.route('/a')
def add_comments():
    q = query_db("CREATE TABLE comment_count (story_id INTEGER PRIMARY KEY, comment_count INTEGER)", [], one=True)
    return "table added"

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

@app.route("/<string:mode>/<string:date_start>")
@app.route("/<string:mode>/<string:date_start>/")
@app.route("/<string:mode>/<string:date_start>/<string:date_end>")
@app.route("/<string:mode>/<string:date_start>/<string:date_end>/")
def stories_list(mode, date_start, date_end=0,home=False):
	if mode == 'day' and date_end == 0: 
		date_end = date_start

	if date_start != 0 and date_end != 0:
		start_datetime 	= datetime.datetime.strptime(date_start,"%Y-%m-%d")
		end_datetime 	= datetime.datetime.strptime(date_end,"%Y-%m-%d")
		start_epoch = format_from_date_time_to_epoch(start_datetime)
		end_epoch 	= calculate_next_midnight_epoch(format_from_date_time_to_epoch(end_datetime))
		day_before	= format_from_date_time_to_string_short(start_datetime - datetime.timedelta(days=1))
		day_after 	= format_from_date_time_to_string_short(start_datetime + datetime.timedelta(days=1))

		if mode == 'day':
			page_header = date_start
			back_button = day_before
			if (end_datetime + datetime.timedelta(days=1)) > datetime.datetime.now():
				forward_button = False
			else:
				forward_button = day_after

		elif mode == 'week':
			page_header = "%s to %s" % (date_start, date_end)
			week_before_start 	= format_from_date_time_to_string_short(start_datetime - datetime.timedelta(days=7))
			week_before_end 	= day_before
			week_after_start 	= format_from_date_time_to_string_short(end_datetime + datetime.timedelta(days=1))
			week_after_end		= format_from_date_time_to_string_short(end_datetime + datetime.timedelta(days=7))
			back_button 		= "%s/%s" % (week_before_start, week_before_end)
			if (end_datetime + datetime.timedelta(days=1)) > datetime.datetime.now():
				forward_button = False
			else:
				forward_button = "%s/%s" % (week_after_start, week_after_end)

		elif mode == 'month':
			page_header = start_datetime.strftime('%Y-%m')
			month_before_start 	= (start_datetime - relativedelta(months=+1)).replace(day=1)
			month_before_end 	= datetime.date(month_before_start.year, month_before_start.month, calendar.monthrange(month_before_start.year, month_before_start.month)[1])
			month_after_start 	= (start_datetime + relativedelta(months=+1)).replace(day=1)
			month_after_end 	= datetime.date(month_after_start.year, month_after_start.month, calendar.monthrange(month_after_start.year, month_after_start.month)[1])
			back_button 		= "%s/%s" % (format_from_date_time_to_string_short(month_before_start), month_before_end)
			if (end_datetime + datetime.timedelta(days=1)) > datetime.datetime.now():
				forward_button = False
			else:
				forward_button = "%s/%s" % (format_from_date_time_to_string_short(month_after_start), month_after_end)

		elif mode == 'year':
			page_header = start_datetime.year
			year_before_start 	= datetime.date((start_datetime.year - 1), 1, 1)
			year_before_end		= datetime.date((start_datetime.year - 1), 12, 31)
			year_after_start 	= datetime.date((start_datetime.year + 1), 1, 1)
			year_after_end 		= datetime.date((start_datetime.year + 1), 12, 31)
			back_button			= "%s/%s" % (format_from_date_time_to_string_short(year_before_start), year_before_end)
			if (end_datetime + datetime.timedelta(days=1)) > datetime.datetime.now():
				forward_button = False
			else:
				forward_button = "%s/%s" % (format_from_date_time_to_string_short(year_after_start), year_after_end)

		else:
			abort(404)

		if home:
			end_epoch = int(time.mktime(datetime.datetime.now().timetuple()))
			start_epoch = end_epoch - 86400
			top_stories = get_top_stories(start_epoch, end_epoch)
		else:
			top_stories = get_top_stories(start_epoch, end_epoch)
		
		top_stories = trim_stories(top_stories,20)
		day_link, week_link, month_link, year_link = get_date_links()

		context = {
					'top_stories': top_stories,
					'page_header': page_header,
					'forward_button': forward_button,
					'back_button': back_button,
					'day_link': day_link,
					'week_link': week_link,
					'month_link': month_link,
					'year_link': year_link,
					'mode': mode,
				}

		if home: 
			context['page_header'] = "The Last 24 Hours"
			context['back_button'] = date_start

		response = make_response (render_template("stories.html",context=context))
		return response
	else:
		abort(404)


# the main page
@app.route("/")
def index():
	return stories_list("day",str(datetime.date.today()),str(datetime.date.today()),True)

if __name__ == "__main__":
	app.run(debug=True)








