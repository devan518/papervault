# papervault
a small app for storing files (still a work in progress)
# WARNING
i was in a rush and i had an error i was stuck on, long story short ai slop coded it, it gives errors.
pls somebody fix them cuz im kinda new to jinja2 and web dev! i really dont wanna abandon this project too. it used to work till ai just had to ruin it 
and halluncinate.
### how to run my bad code
its some pretty bad code and it still doesnt have stuff like password encryption or error handling but i am open sourcing it for any tips. 
for the app to work, 
1.) git clone
2.) add your firebase credentials json in a file named "credentials.json"
3.) do the same but for supabase. make a .env file and add
SUPABASE_URL=https://example.supabase.co
ANON_KEY=jpxfrd
4.) did you get the reference
5.) anyway if you are using vscode, go to the run and debug tab and just click the run button, however if you are using another editor run:
pip install uvicorn
uvicorn main:app --reload

contact me on discord @ eelmo_!
