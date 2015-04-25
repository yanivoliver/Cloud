In addition to the required endpoints, we implemented the following endpoints as part of the admin API.

=== Admin endpoints ===

== Creating a new exercise ==
Accessing the '/exercises/:id' endpoint with PUT (authentication required)
curl http://ubuntu-yanivo.cloudapp.net:8080/exercises/1 -X PUT -u yaron:MCMIITAGWVOUEG -d '{"name":"test exercise 1", "version":"1.0", "comment":"hey"}' -H "Content-Type: application/json"

== Adding a file to an existing exercise ==
Accessing the '/exercises/:id/file' endpoint with PUT (authentication required)
curl http://ubuntu-yanivo.cloudapp.net:8080/exercises/1/file -X PUT -u yaron:MCMIITAGWVOUEG -F manifest=@CloudCheck.js

== Adding a student to an existing exercise ==
Accessing the '/exercises/:id/student' endpoint with PUT (authentication required)
curl http://ubuntu-yanivo.cloudapp.net:8080/exercises/1/student -X PUT -u yaron:MCMIITAGWVOUEG -d '{"name":"zohar","id":"1337"}' -H "Content-Type: application/json"

== Deleting an existing student from an existing exercise ==
Accessing the '/exercises/:id/student/:student' with DELETE entpoint (authentication required)
curl http://ubuntu-yanivo.cloudapp.net:8080/exercises/1/student/1337 -X DELETE -u yaron:MCMIITAGWVOUEG

== Deleting an existing file from an existing exercise ==
Accessing the '/exercises/:id/file/:name' with DELETE entpoint (authentication required)
curl http://ubuntu-yanivo.cloudapp.net:8080/exercises/1/file/CloudCheck.js -X DELETE -u yaron:MCMIITAGWVOUEG
