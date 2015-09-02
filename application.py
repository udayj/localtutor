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


def rewrite_query(query):
	return query

@app.route('/subjects')
def subjects():
	client=MongoClient()
	db=client.local_tutor
	teachers=db.teachers.find()
	output=[]
	output_unique=[]
	try:
		for teacher in teachers:
			match=[subject for subject in teacher['subject']]
			for individual_match in match:
				if individual_match not in output_unique:
					output.append(individual_match)
					output_unique.append(individual_match)
	except StopIteration:
		pass
	return render_template('subjects.html',output=output)

@app.route('/about')
def about():
	
	return render_template('about.html')

@app.route('/search')
def search():
	query=request.args.get('subject')
	if not query or query.strip()=='':
		return render_template('search_error.html')
	client=MongoClient()
	db=client.local_tutor
	query_modified=rewrite_query(query)
	teachers=db.teachers.find({'subject':{'$in':[query]}})
	results=[]
	try:
		for teacher in teachers:
			results.append(teacher)
	except StopIteration:
		return render_template('search_error.html')
	return render_template('search_result.html',results=results,query=query,length=(len(results)+1)/2)

@app.route('/options')
def options():
	q=request.args.get('subject')
	q=q.strip().lower()
	client=MongoClient()
	db=client.local_tutor
	
	pattern=re.compile('.*'+q+'.*')
	
	teachers=db.teachers.find({'subject':{'$in':[pattern]}})
	
	output=[]
	output_unique=[]
	try:
		for teacher in teachers:
			match=[subject for subject in teacher['subject'] if re.search(pattern,subject)]
			for individual_match in match:
				if individual_match not in output_unique:
					output.append({'value':individual_match})
					output_unique.append(individual_match)
	except StopIteration:
		pass

	app.logger.debug(output)
	js=json.dumps(output)
	
	resp=Response(js,status=200,mimetype='application/json')
	return resp
		

if __name__ == "__main__":
    app.run()