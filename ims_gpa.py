import requests
from PIL import Image
from bs4 import BeautifulSoup
from tabulate import tabulate
from jinja2 import Environment, FileSystemLoader
import pytesseract
import cv2
import pandas as pd
from matplotlib import pyplot as plt
import seaborn as sns
import os
import pdfkit

URL = "https://imsnsit.org/imsnsit/studentsnapshot.php"

def decode(soup):
    # Download captcha image
    captcha_img_src = soup.find(id='captchaimg')['src']
    captcha_img_url = "https://imsnsit.org/imsnsit/" + captcha_img_src
    captcha_img = requests.get(captcha_img_url)

    # Write captcha image to a file
    with open("captcha.jpg", 'wb') as f:
        f.write(captcha_img.content)

    # Decode captcha using ocr
    img = Image.open('./captcha.jpg').convert('L')
    img = img.resize((225, 81))
    img.save('captcha.jpg', 'JPEG', optimized=True)
    ocr_img = Image.open('./captcha.jpg')
    captcha = pytesseract.image_to_string(ocr_img)

    # cleaning captcha
    captcha = captcha.strip()
    captcha = captcha.replace(" ", "")
    captcha = ''.join(c for c in captcha if c.isdigit())
    return captcha

def take_details():
    details = {}
    details['roll_number'] = input('Enter Roll Number : ')
    details['father_number'] = input('Enter Father Phone Number : ')
    return details

# Grade to weighted credit mapping
grade_map = {
    'O': 10,
    'A+': 9,
    'A': 8,
    'B+': 7,
    'B': 6,
    'C': 5,
    'D': 4,
    'F': 0
}

def calculateSGPA(credits, grades):
    # Get weights for grades
    weights = [grade_map[grade] for grade in grades]
    weighted_credits = 0
    for i in range(len(weights)):
        weighted_credits += (weights[i] * credits[i])
    return weighted_credits, round(weighted_credits/sum(credits), 2)

page = requests.get(URL)
soup = BeautifulSoup(page.content, 'html.parser')
captcha = decode(soup)
details = take_details()

# NOTE: Seems like we can bypass captcha by just sending space for the 'cap' field in the form data lmao
# Therefore requests.Session() method is ignored since in that case we'll need the correct captcha, which will take multiple tries using pytesseract

# Make post request with data to form
form_dict = {
    'entitycode': details['roll_number'], 
    'phone': details['father_number'], 
    'cap': ' ', #'cap': captcha 
    'submit': 'Go', 
    'rty': 'StudentAttendence',
    'typ': 'Attendence'
}
headers = {
    'User-Agent': 'Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/77.0.3865.90 Mobile Safari/537.36',
    'Content-Type': 'application/x-www-form-urlencoded'
}
r = requests.post(URL, data=form_dict, headers=headers)
soup = BeautifulSoup(r.content, 'html.parser')
# print(soup.prettify())
# Scrape student details
detail_table = soup.select('tr.list-data')
student = detail_table[0]
detail_tags = student.findAll('td')
student_details = {
    'Name': detail_tags[0].get_text(),
    'Roll Number': detail_tags[1].get_text()
}
student = detail_table[2]
detail_tags = student.findAll('td')
student_details['Department'] = detail_tags[0].get_text()[13:-3]
student_details['Programme'] = detail_tags[1].get_text()[12:-1]

# Scrape performance details

# Get all tables since the HTML being returned by the website is faulty we cannot directly acces the performance tables
performance_table = soup.find_all('table')

# The required tables start from index 4 but we need to check for how many semesters result has been declared to save only the necessary tables
semesters_declared = 0
for tag in performance_table:
    heading = tag.find(class_='plum_head')
    if(heading != None):
        if(heading.get_text().startswith('Semester')):
            semesters_declared += 1
end_index = 4 + semesters_declared
performance_table = performance_table[4: end_index]

# Each semester will be represented by a dictionary
all_semesters = []
dataframes = []

for tag in performance_table:
    semester_details = {
        'subject': [],
        'credits': [],
        'grade_acquired': []
    }
    subjects = tag.findAll(class_='plum_fieldbig')
    for i in range(len(subjects) - 2):
        tags = subjects[i].findAll('td')
        info = [tag.get_text() for tag in tags]
        semester_details['subject'].append(info[0])
        semester_details['credits'].append(int(info[1]))
        semester_details['grade_acquired'].append(info[2])
        semester_details['weighted_credits'], semester_details['sgpa'] = calculateSGPA(semester_details['credits'], semester_details['grade_acquired'])
    all_semesters.append(semester_details)
    df = pd.DataFrame(semester_details)
    df = df.drop(['weighted_credits', 'sgpa'], axis='columns')
    dataframes.append(df)

cumulative_weights = 0
cumulative_credits = 0
for sem in all_semesters:
    cumulative_credits += sum(sem['credits'])
    cumulative_weights += sem['weighted_credits']
CGPA = round(cumulative_weights / cumulative_credits, 2)

print(f"Student Name : {student_details['Name']}")
print(f"Roll Number : {student_details['Roll Number']}")
print(f"Branch/Department : {student_details['Department']}")
print(f"Programme: {student_details['Programme']}")

SGPAs = []
semesters = []

for index, df in enumerate(dataframes):
    print(tabulate(df, headers='keys', tablefmt='psql'))
    sgpa = all_semesters[index]['sgpa']
    SGPAs.append(sgpa)
    semesters.append(index+1)
    print(f"SGPA for semester {index + 1} = {sgpa}")
print(f"CGPA after {semesters_declared} semesters = {CGPA}")

# Visualization / Plots

# Merge all semester dfs into one for easier and more options of visualization
df = pd.concat(dataframes)
df.columns = ['Subject', 'Credits', 'Grade']
df = df.reset_index()
# Plotting count of grades acquired over all semesters
sns.set()
fig = plt.figure(figsize=(5, 5))
sns.countplot(df.Grade)
plt.title('Counts of grades acquired over all semesters')
fig.savefig(os.listdir()[0] + '/templates/figure1.png', dpi=fig.dpi)
# Plotting progression of sgpa over semesters
tdf = pd.DataFrame({
    'Semester': semesters,
    'SGPA': SGPAs
})
fig = plt.figure(figsize=(5, 5))
sns.lineplot(x='Semester', y='SGPA', data=tdf)
plt.title('SGPA Progression over all semesters')
fig.savefig(os.listdir()[0] + '/templates/figure2.png', dpi=fig.dpi)

# Generate PDF Report - (Student Data, Dataframes, SGPA, CGPA, Data Visualizations)

# First create a HTML file using jinja2 templating which is later converted to a pdf.
env = Environment(loader=FileSystemLoader(os.listdir()[0] + '/templates'))
template = env.get_template('report.html')
data = {
    'name': student_details['Name'],
    'roll_number': student_details['Roll Number'],
    'department': student_details['Department'],
    'programme': student_details['Programme'],
    'semesters': semesters,
    'sgpas': SGPAs,
    'dfs': [df.to_html(classes=['table', 'table-bordered']) for df in dataframes],
    'cgpa': CGPA
}
output = template.render(data=data)

# Save to html
with open(os.listdir()[0] + '/templates/final_report.html', 'w') as f:
    f.write(output)

pdfkit.from_file(os.listdir()[0] + '/templates/final_report.html', os.listdir()[0] + '/report.pdf')
print('Your performance PDF report is ready! Check the report.pdf file in the script directory!')