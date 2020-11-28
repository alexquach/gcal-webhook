https://developers.google.com/calendar/v3/push
https://stackabuse.com/deploying-a-flask-application-to-heroku/
https://blog.bearer.sh/consume-webhooks-with-python/
https://stackoverflow.com/a/31951477
https://devcenter.heroku.com/articles/heroku-postgresql#set-up-postgres-on-windows
https://www.youtube.com/watch?v=w25ea_I89iM

# to look at
https://developers.google.com/calendar/v3/sync
https://www.postgresqltutorial.com/postgresql-python/insert/#:~:text=To%20insert%20a%20row%20into%20a%20PostgreSQL%20table,returns%20a%20new%20instance%20of%20the%20connection%20class.

https://developers.google.com/calendar/v3/push
https://developers.google.com/calendar/v3/reference

$ heroku git:remote -a {your-project-name}
$ git push heroku master

Need to set config vars for env vars
JSON
echo $GOOGLE_CREDENTIALS > service-account-credentials.json