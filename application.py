from flask import Flask, request, render_template, Response, redirect, url_for,flash, jsonify
from pymongo import MongoClient
import re
import json

SECRET_KEY='SECRET'


SALT='123456789passwordsalt'

app = Flask(__name__)
app.debug=True

@app.route('/')
def main_page():
	return render_template('main_page.html')



@app.route('/search')
def search():
	query=request.args.get('subject')
	if not query or query.strip()=='':
		return render_template('search_error.html')
	client=MongoClient()
	db=client.local_tutor
	teachers=db.teachers.find({'subject':query})
	results=[]
	try:
		for teacher in teachers:
			results.append(teacher)
	except StopIteration:
		return render_template('search_error.html')
	return render_template('search_result.html',results=results,query=query)

@app.route('/options')
def options():
	q=request.args.get('subject')
	q=q.strip().lower()
	client=MongoClient()
	db=client.local_tutor
	
	pattern=re.compile('.*'+q+'.*')
	
	teachers=db.teachers.find({'subject':pattern})
	
	output=[]
	output_unique=[]
	try:
		for teacher in teachers:
			if teacher['subject'].strip() not in output_unique:
				output.append({'value':teacher['subject'].strip()})
				output_unique.append(teacher['subject'].strip())
	except StopIteration:
		pass

	app.logger.debug(output)
	js=json.dumps(output)
	
	resp=Response(js,status=200,mimetype='application/json')
	return resp
		

if __name__ == "__main__":
    app.run()