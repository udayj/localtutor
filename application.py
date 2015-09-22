from flask import Flask, request, render_template, Response, redirect, url_for,flash, jsonify
from pymongo import MongoClient
from flask.ext.login import (LoginManager, current_user, login_required,
                            login_user, logout_user, UserMixin, confirm_login,
                             fresh_login_required,login_url)
from bson.objectid import ObjectId
import re
import json
from datetime import datetime,timedelta
import codecs
import os
from itsdangerous import URLSafeTimedSerializer
import operator

SECRET_KEY='SECRET'


SALT='123456789passwordsalt'

app = Flask(__name__)
app.debug=True
app.secret_key=SECRET_KEY


REMEMBER_COOKIE_DURATION=timedelta(days=365)
login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.login_message = u"Please log in to access this page."

login_serializer = URLSafeTimedSerializer(SECRET_KEY)

class User(UserMixin):
    def __init__(self, name, _id, fb_id,active=True):
        self.name = name
        self.id = _id
        self.fb_id=fb_id
        self.active=active
    
    def is_active(self):
        return self.active
        
    
    def get_auth_token(self):
        """
        Encode a secure token for cookie
        """
        data = [str(self.id), self.fb_id]
        return login_serializer.dumps(data)

@login_manager.user_loader
def load_user(_id):

	app.logger.debug("in load_user")
	client=MongoClient()
	db=client.local_tutor
	user=db.users.find({'_id':ObjectId(_id)})
	try:
		user=user.next()
		
		ret_user=User(name=user['name'],fb_id=user['fb_id'],_id=str(user['_id']),active=True)
		return ret_user
	except StopIteration:
		return None

@login_manager.token_loader
def load_token(token):
    """
    Flask-Login token_loader callback. 
    The token_loader function asks this function to take the token that was 
    stored on the users computer process it to check if its valid and then 
    return a User Object if its valid or None if its not valid.
    """
    app.logger.debug("in load_token")
    #The Token itself was generated by User.get_auth_token.  So it is up to 
    #us to known the format of the token data itself.  
 
    #The Token was encrypted using itsdangerous.URLSafeTimedSerializer which 
    #allows us to have a max_age on the token itself.  When the cookie is stored
    #on the users computer it also has a exipry date, but could be changed by
    #the user, so this feature allows us to enforce the exipry date of the token
    #server side and not rely on the users cookie to exipre. 
    max_age = REMEMBER_COOKIE_DURATION.total_seconds()
 
    #Decrypt the Security Token, data = [username, hashpass]
    data = login_serializer.loads(token, max_age=max_age)
 
    #Find the User
    user = load_user(data[0])
 
    #Check Password and return user or None
    if user and data[1] == user.fb_id:
        return user
    return None

login_manager.init_app(app)

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
			if len(teacher_parts)<12:
				continue
			teacher_structured={}
			fields=['subject','name','contact_number','email','age_group','venue',
			'classroom_type','geographical_location','area','usp','teacher_type','price']
			counter=0
			count=count+1
			for field in fields:
				if counter==0:
					parts=teacher_parts[counter].lower().strip().split(',')
					subjects=[part.lower().strip() for part in parts]
					teacher_structured[field]=subjects
					for subject in subjects:
						prior_subject_count=db.subjects.find({'name':subject}).count()
						if prior_subject_count<=0:
							db.subjects.save({'name':subject,'category':''})

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

@app.route('/login',methods=['POST'])
def login():

	data={}
	for name,value in dict(request.form).iteritems():
		data[name]=value[0].strip()
	app.logger.debug(str(data))

	client=MongoClient()
	db=client.local_tutor
	if 'fb_user_id' not in data or 'fb_user_name' not in data or 'redirect_url' not in data:
		return render_template('error.html')
	user=db.users.find({'fb_id':data['fb_user_id']})
	try:
		user=user.next()
		ret_user=User(name=user['name'],_id=str(user['_id']),fb_id=user['fb_id'])
		app.logger.debug(ret_user.name)
		app.logger.debug(ret_user.id)
		app.logger.debug(ret_user.fb_id)
		app.logger.debug(ret_user.active)
		if login_user(ret_user,force=True):
			return redirect(data['redirect_url'])
		else:
			return render_template('error.html')
	except StopIteration:
		user={}
		user['fb_id']=data['fb_user_id']
		user['name']=data['fb_user_name']
		_id=db.users.save(user)
		ret_user=User(name=user['name'],_id=_id,fb_id=user['fb_id'])
		app.logger.debug(ret_user)
		app.logger.debug(ret_user.active)
		if login_user(ret_user, force=True):
			return redirect(data['redirect_url'])
		else:
			return render_template('error.html')
	
@app.route('/logout')
def logout():
	logout_user()
	flash("Logged out!")
	redirect_url=request.args.get('redirect_url')
	if redirect_url is not None:
		return redirect(redirect_url)
	redirect('/')

def rewrite_query(query):
	client=MongoClient()
	db=client.local_tutor
	query=query.lower()
	category_count=db.subjects.find({'category':query}).count()
	if category_count<=0:
		return [query]
	subjects=db.subjects.find({'category':query})
	output=[]
	for subject in subjects:
		output.append(subject['name'])
	
	subjects=db.subjects.find({'name':query})
	for subject in subjects:
		output.append(subject['name'])
	return output

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
	def sorter(item):
		category, subjects = item
		return len(subjects)
	client=MongoClient()
	db=client.local_tutor
	subjects=db.subjects.find()
	output=[]
	for subject in subjects:
		output.append(subject['name'])
	output.sort()
	category_wise={}
	subjects=db.subjects.find()
	for subject in subjects:
		if len(subject['category'])>1:
			if subject['category'] not in category_wise:
				category_wise[subject['category']]=[]
			category_wise[subject['category']].append(subject['name'])
	print category_wise.items()
	sorted_category_wise=sorted(category_wise.items(),key=sorter)

	return render_template('subjects.html',output=output,category_wise=sorted_category_wise)

@app.route('/save_category',methods=['POST'])
def save_category():
	data={}
	for name,value in dict(request.form).iteritems():
		data[name]=value[0].strip().lower()
	app.logger.debug(str(data))
	client=MongoClient()
	db=client.local_tutor

	subject=db.subjects.find({'name':data['subject']})
	try:

		subject=subject.next()
		subject['category']=data['category']
		db.subjects.save(subject)
	except StopIteration:
		app.logger.error('problem saving subject category for '+data['subject'])
		response={'result':'failed'}
		js=json.dumps(response)
		resp=Response(js,status=200,mimetype='application/json')
		return resp		

	response={'result':'success'}
	js=json.dumps(response)
	resp=Response(js,status=200,mimetype='application/json')
	return resp



@app.route('/subject_category')
def subject_category():

	def sorter(subject):
		return subject['name']
	client=MongoClient()
	db=client.local_tutor
	subjects=db.subjects.find()
	output=[]
	for subject in subjects:
		output.append(subject)
	output.sort(key=sorter)
	return render_template('subject_category.html',subjects=output)

@app.route('/create_subjects')
def create_subjects():
	password=request.args.get('password')

	if password!='createsubjectstutorack':
		return render_template('error.html')

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
	output.sort()
	for subject in output:
		prior_subject_count=db.subjects.find({'name':subject}).count()
		if prior_subject_count<=0:
			db.subjects.save({'name':subject,'category':''})
	return render_template('success_subject.html')

@app.route('/about')
def about():
	
	return render_template('about.html')

@app.route('/associate_student_tutor',methods=['POST'])
def associate_student_tutor():
	data={}
	for name,value in dict(request.form).iteritems():
		data[name]=value[0].strip()
	app.logger.debug(str(data))
	client=MongoClient()
	db=client.local_tutor
	if 'tutor_id' not in data or 'student_id' not in data:
		response={}
		response={'result':'failed'}
		js=json.dumps(response)
		resp=Response(js,status=200,mimetype='application/json')
		return resp

	tutor_id=data['tutor_id']
	student_id=data['student_id']
	association=db.student_tutor.find({'tutor_id':tutor_id,'student_id':student_id}).count()
	if association>0:
		app.logger.error('Extra entries for student tutor association '+tutor_id+' '+student_id)
		response={}
		response={'result':'success'}
		js=json.dumps(response)
		resp=Response(js,status=200,mimetype='application/json')
		return resp
	association={}
	association['tutor_id']=tutor_id
	association['student_id']=student_id
	db.student_tutor.save(association)
	response={}
	response={'result':'success'}
	js=json.dumps(response)
	resp=Response(js,status=200,mimetype='application/json')
	return resp

@app.route('/disassociate_student_tutor',methods=['POST'])
def disassociate_student_tutor():
	data={}
	for name,value in dict(request.form).iteritems():
		data[name]=value[0].strip()
	app.logger.debug(str(data))
	client=MongoClient()
	db=client.local_tutor
	if 'tutor_id' not in data or 'student_id' not in data:
		response={}
		response={'result':'failed'}
		js=json.dumps(response)
		resp=Response(js,status=200,mimetype='application/json')
		return resp

	tutor_id=data['tutor_id']
	student_id=data['student_id']

	association=db.student_tutor.find({'tutor_id':tutor_id,'student_id':student_id}).count()
	if association==0:
		app.logger.error('No entries for student tutor association '+tutor_id+' '+student_id)
		response={}
		response={'result':'success'}
		js=json.dumps(response)
		resp=Response(js,status=200,mimetype='application/json')
		return resp
	num=db.student_tutor.remove({'tutor_id':tutor_id,'student_id':student_id})
	app.logger.debug(str(num)+' student teacher associations removed')
	response={}
	response={'result':'success'}
	js=json.dumps(response)
	resp=Response(js,status=200,mimetype='application/json')
	return resp

@app.route('/friend_tutor',methods=['POST'])
def friend_tutor():
	data={}
	for name,value in dict(request.form).iteritems():
		data[name]=[element.strip() for element in value]
	app.logger.debug(str(data))
	client=MongoClient()
	db=client.local_tutor
	if 'friends[]' not in data or 'tutors[]' not in data:
		response={}
		response={'result':'success'}
		response['friend_tutor']=[]
		js=json.dumps(response)
		resp=Response(js,status=200,mimetype='application/json')
		return resp
	friends=data['friends[]']
	tutors=data['tutors[]']
	result=[]
	for tutor in tutors:
		for friend in friends:
			count=db.student_tutor.find({'tutor_id':tutor,'student_id':friend}).count()
			if count>0:
				result.append(tutor)
				break
	print result
	response={}
	response={'result':'success'}
	response['friend_tutor']=result
	js=json.dumps(response)
	resp=Response(js,status=200,mimetype='application/json')
	return resp

@app.route('/friend_tutor_name',methods=['POST'])
def friend_tutor_name():
	data={}
	counter=0
	for name,value in dict(request.form).iteritems():
		if name=='tutor':
			data[name]=value[0].strip()
		else:
			data[name]=[element.strip() for element in value]
	app.logger.debug(str(data))
	client=MongoClient()
	db=client.local_tutor
	if 'friends[]' not in data or 'tutor' not in data:
		response={}
		response={'result':'success'}
		response['friend_tutor']=[]
		js=json.dumps(response)
		resp=Response(js,status=200,mimetype='application/json')
		return resp
	friends=data['friends[]']
	tutor=data['tutor']
	result=[]
	for friend in friends:
		count=db.student_tutor.find({'tutor_id':tutor,'student_id':friend}).count()
		if count>0:
			result.append(friend)
			
	print result
	response={}
	response={'result':'success'}
	response['friend_tutor']=result
	js=json.dumps(response)
	resp=Response(js,status=200,mimetype='application/json')
	return resp


@app.route('/tutor')
def tutor():
	tutor_id=request.args.get('id')
	client=MongoClient()
	db=client.local_tutor
	if tutor_id is None:
		return render_template('error.html')
	tutor=db.teachers.find({'_id':ObjectId(tutor_id)})
	try:
		tutor=tutor.next()
		return render_template('tutor.html',tutor=tutor)
	except StopIteration:
		return render_template('error.html')


@app.route('/search')
def search():
	query=request.args.get('subject')
	if not query or query.strip()=='':
		return render_template('search_error.html')
	client=MongoClient()
	db=client.local_tutor

	query_modified=rewrite_query(query)
	
	teachers=db.teachers.find({'subject':{'$in':query_modified}})
	results=[]
	try:
		for teacher in teachers:
			results.append(teacher)
	except StopIteration:
		return render_template('search_error.html')
	student_tutor_assoc={}
	if hasattr(current_user,'id'):
		for teacher in results:
			student_teacher=db.student_tutor.find({'tutor_id':str(teacher['_id']),'student_id':current_user.fb_id}).count()
			if student_teacher>0:
				student_tutor_assoc[teacher['_id']]=True
	print student_tutor_assoc
	return render_template('search_result.html',results=results,query=query,length=(len(results)+1)/2,
							student_tutor_assoc=student_tutor_assoc)	

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