import os


#Cloning Github Page

os.system("git clone --branch v0.1 --recursive https://github.com/daniel-kukiela/nmt-chatbot.git")

#preparing Data
os.system("cd nmt-chatbot && pip install -r requirements.txt && cd setup && python prepare_data.py")

#Copying The Files
os.system("cp  misc_utils.py nmt-chatbot/nmt/nmt/utils/misc_utils.py")

#Training
os.system("python nmt-chatbot/train.py")


os.system("python nmt-chatbot/inference.py")
