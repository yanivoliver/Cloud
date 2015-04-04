// TODO: Ask Yaron about the displaying of the 'completed' attribute in exercises
// TODO: Make sure all responses are JSON responses

var mongo = require('mongodb').MongoClient;
var express = require('express');
var auth = require('basic-auth');
var body_parser = require('body-parser')
var assert = require('assert');

ENDPOINTS = {'GET': {'/ping': ping_handler, '/': endpoints_handler, '/exercises': get_exercises_handler},
			 'PUT': {'/exercises/:id': exercise_add_handler, '/exercises/:id/student': add_student_to_excersise_handler},
			 'DELETE': {}};

SECURE_ENDPOINTS = {'GET': {'/ping': false, '/': false, '/exercises': false},
					'PUT': {'/exercises/:id': true, '/exercises/:id/student': true},
					'DELETE': {}};

SERVER_PORT = 8080;

MONGODB_URL = 'mongodb://localhost:27017/cloudcheck';

USERNAME = 'yaron';
PASSWORD = 'MCMIITAGWVOUEG';

var app = express(); 
load_endpoints(app);

var server = app.listen(SERVER_PORT, function() {
	var host = server.address().address;
	var port = server.address().port;
	console.log('CloudCheck listening at http://%s:%s', host, port);
});

function load_endpoints(app) {
	app.use(body_parser.json());

	for (var key in ENDPOINTS['GET']) {
		if (SECURE_ENDPOINTS['GET'][key]) {
			app.get(key, auth_handler);
		}
    	app.get(key, ENDPOINTS['GET'][key]);
	}
	for (var key in ENDPOINTS['PUT']) {
		if (SECURE_ENDPOINTS['PUT'][key]) {
			app.put(key, auth_handler);
		}		
	    app.put(key, ENDPOINTS['PUT'][key]);
	}
	for (var key in ENDPOINTS['DELETE']) {
		if (SECURE_ENDPOINTS['DELETE'][key]) {
			app.delete(key, auth_handler);
		}		
	    app.delete(key, ENDPOINTS['DELETE'][key]);
	}
}

function auth_handler(req, res, next) {
	var credentials = auth(req);

	if (credentials.name != USERNAME || credentials.pass != PASSWORD) {
		res.status(403).json('Invalid username or password');
		return;
	}

	next();
}

function ping_handler(req, res) {
	res.json({'ping': 'pong'});
}

function endpoints_handler(req, res) {
	var endpoints = {"endpoints": []}
	for (var type in ENDPOINTS) {
		for (var endpoint in ENDPOINTS[type]) {
			endpoints["endpoints"].push(type + " " + endpoint);
		}
	}
	res.json(endpoints);
}

// TODO: Handler completed=true flag as well
function get_exercises_handler(req, res) {
	var get_exercises = function(db) { 
		var collection = db.collection('exercises');
		collection.find({},{'id': 1, 'name': 1, 'version': 1, '_id': 0}).toArray(function(err, docs) {
    		assert.equal(err, null);
    		res.json(docs);
		}); 
	}

	mongo.connect(MONGODB_URL, function(err, db) {
		assert.equal(null, err);
		get_exercises(db);
	});	

}

function exercise_add_handler(req, res) {
	var insert_document = function(db, record) { 
		var collection = db.collection('exercises');
		collection.insert(record, function(err, result) {
		    assert.equal(err, null);
			console.log("Inserted exercise document");
			res.send("Inserted new exercise");
			db.close();
		});
	}

	// TODO: Check if req.params.id already exists in the DB. If so, override it
	if (req.body.hasOwnProperty('name') && req.body.hasOwnProperty('version') && req.body.hasOwnProperty('comment')) {
		var record = {'id': req.params.id,
					  'name': req.body.name,
					  'version': req.body.version,
					  'comment': req.body.comment,
					  'published_at': new Date().toISOString(),
					  'completed': false,
					  'files': [],
					  'students': [] };

		mongo.connect(MONGODB_URL, function(err, db) {
			assert.equal(null, err);
			insert_document(db, record);
		});	
	} else {
		res.status(400).send("Missing required fields");
	}
}

// TODO: Handle errors, such as invalid exercise id
function add_student_to_excersise_handler(req, res) {
	var update_document = function(db, exercise_id, student) { 
		var collection = db.collection('exercises');
		collection.find({'id': exercise_id}).toArray(function(err, docs) {
		    assert.equal(err, null);
		    assert.equal(1, docs.length);
		    console.log("Found the following records");
		    console.dir(docs);

		    var students = docs[0].students;
		    students.push(student);
		    
    		collection.update({'id': exercise_id}, { $set: { 'students': students } }, function(err, result) {
			    assert.equal(err, null);
				console.log("update exercise student");
				res.send("update new student to exercise");
				db.close();
			});
		});      
	}

	if (req.body.hasOwnProperty('name') && req.body.hasOwnProperty('id')) {
		var record = {'id': req.body.id,
					  'name': req.body.name };

		mongo.connect(MONGODB_URL, function(err, db) {
			assert.equal(null, err);
			update_document(db, req.params.id, record);
		});	
	} else {
		res.status(400).send("Missing required fields");
	}

}
