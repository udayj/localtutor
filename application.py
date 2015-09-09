from flask import Flask, request, render_template, Response, redirect, url_for,flash, jsonify
from pymongo import MongoClient
import re
import json
from datetime import datetime
import codecs
import os

SECRET_KEY='SECRET'


SALT='123456789passwordsalt'

app = Flask(__name__)
app.debug=True

def content_entry(file_name,db_name):
	f=codecs.open(file_name,'r','utf-8')
	client=MongoClient()
	db=client[db_name]
	count=0
	try:
		while True:
			teacher=f.readline()
			if not teacher:
				break
			teacher_parts=teacher.split('\t')
			if len(teacher_parts)<11:
				continue
			teacher_structured={}
			fields=['subject','name','contact_number','email','age_group','venue',
			'classroom_type','geographical_location','usp','teacher_type','price']
			counter=0
			count=count+1
			for field in fields:
				if counter==0:
					parts=teacher_parts[counter].lower().strip().split(',')

					teacher_structured[field]=[part.lower().strip() for part in parts]
				elif counter==2:
					parts=teacher_parts[counter].lower().strip().split(',')
					teacher_structured[field]=[part.lower().strip() for part in parts]
				else:	
					teacher_structured[field]=teacher_parts[counter].lower().strip()
				counter=counter+1
			
			db.teachers.save(teacher_structured)
	except Exception:
		return -100
	
	return count


@app.route('/')
def main_page():
	return render_template('main_page.html')


def rewrite_query(query):
	return query

@app.route('/upload')
def upload():
	return render_template('upload.html')

@app.route('/upload_staging',methods=['POST'])
def upload_staging():
	data={}
	for name,value in dict(request.form).iteritems():
		data[name]=value[0].strip()
	app.logger.debug(str(data))

	if 'password' not in data:
		js=json.dumps({'result':'failed','message':'Cannot authenticate'})
		resp=Response(js,status=200,mimetype='application/json')
		return resp
	if data['password']!='uploadtutorack':
		js=json.dumps({'result':'failed','message':'Cannot authenticate'})
		resp=Response(js,status=200,mimetype='application/json')
		return resp

	attachment=request.files['attachment']
	#save file -> call routine with that file name for staging db -> if no error -> call routine with that file name for prod db
	#return stats based on error/success
	app.logger.debug(attachment.filename)
	attachment_name='attachment_'+attachment.filename+str(datetime.now().time())
	attachment.save(os.path.join('data',attachment_name))
	ret=content_entry(os.path.join('data',attachment_name),'localtutor')
	response={}
	if ret>=0:
		ret=content_entry(os.path.join('data',attachment_name),'local_tutor')
		if ret>=0:
			response['result']='success'
			response['message']='Data uploaded into the database - '+str(ret)+' rows uploaded'
			
		else:
			print "problem with data entry in production database"
			response['result']='failed'
			response['message']='Data could not be uploaded - database might be in an inconsistent state'
	else:
		response['result']='failed'
		response['message']='No data uploaded'

	print response
	js=json.dumps(response)
	resp=Response(js,status=200,mimetype='application/json')
	return resp

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