from google.cloud import vision
import io
import os
import re
import glob
import string
import json
import requests
import cv2
import sys
from google.protobuf.json_format import MessageToDict
import dateutil.parser
import datetime

# -*- coding: utf-8 -*-

# Configure environment for google cloud vision
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "client_secrets.json"

# Create a ImageAnnotatorClient
VisionAPIClient = vision.ImageAnnotatorClient()

path = 'statement_images'

for filename in glob.glob(os.path.join(path, '*.*')):

    with io.open(filename, 'rb') as image_file:
        content = image_file.read()

    img = cv2.imread(filename)
    # Send the image content to vision and stores text-related response in text
    image = vision.types.Image(content=content)
    response = VisionAPIClient.document_text_detection(image=image)

    # Converts google vision response to dictionary
    response = MessageToDict(response, preserving_proto_field_name=True)

    document = response.get('full_text_annotation')
    # print(document)
    # to identify and compare the break object (e.g. SPACE and LINE_BREAK) obtained in API response
    breaks = vision.enums.TextAnnotation.DetectedBreak.BreakType

    # generic counter
    c = 0

    # List of lines extracted
    lines = []

    # List of corresponding confidence scores of lines
    confidence = []

    # Initialising list of lines
    lines.append('')

    # Initialising list of confidence scores
    confidence.append(2)

    bounding_box = []
    bounding_box.append([])
    try:
        page = document.get('pages')
    except Exception as e:
        print("Bad Image")
        sys.exit(1)
    for page in document.get('pages'):
        for block in page.get('blocks'):
            for paragraph in block.get('paragraphs'):
                for word in paragraph.get('words'):
                    for symbol in word.get('symbols'):
                        lines[c] = lines[c] + symbol.get('text')
                        bounding_box[c].append(symbol.get(
                            'bounding_box', {}).get('vertices'))

                        if re.match(r'^[a-zA-Z]+\Z', symbol.get('text')) or symbol.get('text').isdigit():
                            confidence[c] = min(
                                confidence[c], symbol.get('confidence', 0))
                        if symbol.get('property', {}).get('detected_break', {}).get('type') == 'LINE_BREAK' or \
                                symbol.get('property', {}).get('detected_break', {}).get('type') == 'EOL_SURE_SPACE':
                            c += 1
                            lines.append('')
                            confidence.append(2)
                            bounding_box.append([])
                        elif symbol.get('property', {}).get('detected_break', {}).get('type') == 'SPACE' or \
                                symbol.get('property', {}).get('detected_break', {}).get('type') == 'SURE_SPACE':
                            lines[c] = lines[c] + ' '

    # Total number of lines
    linecount = len(lines)

    # Initialising all variablese
    raw = ''  # To store all lines
    checktext = ''  # Generic string variable to store surrounding lines
    word_box = []
    overall_x_min = 10000
    overall_x_max = -10000
    # Loop through all lines to check for all required fields
    for index, line in enumerate(lines):

        # To store all lines for exporting later as raw output
        raw = raw + line + "\n"

        # Total number of characters in line
        length = len(line)

        letter_counter = 0
        x_min = 10000
        x_max = -10000
        y_min = 10000
        y_max = -10000

        for boxes in bounding_box[index]:
            # print(boxes)
            if letter_counter < 8:
                for point in boxes:
                    x_min = min(point.get('x'), x_min)
                    x_max = max(point.get('x'), x_max)
                    y_min = min(point.get('y'), y_min)
                    y_max = max(point.get('y'), y_max)
            letter_counter = letter_counter + 1
        word_box.append((x_min, x_max, y_min, y_max))
        overall_x_min = min(overall_x_min, x_min)
        overall_x_max = max(overall_x_max, x_max)
        # wdt = x_max - x_min
        # ht = y_max - y_min
        # print(x_min, x_max, y_min, y_max, " | ", max(0,y_min-int(3.5*ht)),y_min, x_min,x_max+int(wdt/2))
        # height, width, _ = img.shape
        # if wdt > ht:
        #     img1 = img[y_max: min(height, y_max+int(3.5*ht)), x_min:x_max+int(wdt/2)]
        # else:
        #     img1 = img[y_min:y_max+int(ht/2), max(0, x_min-3*wdt):x_min]

        # img1 = img[y_min:y_max, x_min:x_max]
        # cv2.imwrite(filename, img)
    wdt = overall_x_max - overall_x_min
    # print(overall_x_min, overall_x_max, wdt)
    date_list = []
    formatted_date_list = []
    balance_list = []
    for word, box in zip(lines, word_box):
        # print(word, box)
        # print(box[0], overall_x_min + wdt * 0.1, word.count('/'), word.count('-'))
        if box[0] < (overall_x_min + wdt * 0.1) and (word.split()[0].count('/') == 2 or word.split()[0].count('-') == 2):
            date_list.append((word, (box[2]+box[3])/2, box))
            # print(word.count('/'), word.count('-'), word)
            try:
                parsed_date = dateutil.parser.parse(word.split()[0], dayfirst = True)
            except Exception as e:
                parsed_date = formatted_date_list[-1]
            formatted_date_list.append(parsed_date)
        if box[1] > (overall_x_max - wdt * 0.1) and word.count('.') == 1:
            balance_list.append((word, (box[2]+box[3])/2, box))

    # print(date_list)
    transaction_list = []
    for date, formatted_date in zip(date_list, formatted_date_list):
        row = [date]
        transactions = [(date[0], (date[2][0]+date[2][1])/2)]
        corresponding_balance = balance_list[0]
        for balance in balance_list:
            if abs(balance[1] - date[1]) < abs(corresponding_balance[1] - date[1]):
                corresponding_balance = balance
        for word, box in zip(lines, word_box):
            if (min(date[1],corresponding_balance[1])*0.98 <= (box[2]+box[3])/2 <= 1.02* max(date[1],corresponding_balance[1])) \
                and word != date[0] and word != corresponding_balance[0]:
                row.append((word, (box[2]+box[3])/2, box))
                transactions.append((word, (box[0]+box[1])/2))
        transactions.append((corresponding_balance[0], (corresponding_balance[2][0]+corresponding_balance[2][1])/2))
        row.append(corresponding_balance)
        transactions.sort(key = lambda x: x[1])
        transaction_list.append([formatted_date] + [x[0] for x in transactions])

    transaction_list.sort(key = lambda x: x[0])
    result_list = []
    for i, item in enumerate(transaction_list):
        if i > 0:
            cumumlative = cumumlative + (item[0] - transaction_list[i-1][0]).days * int(str(re.sub("\D", "", transaction_list[i-1][-1]))) / 100
        else:
            cumumlative = 0
        print(item[1:])
        trans_dict = {
            "amount" : int(str(re.sub("\D", "", item[-2]))) / 100,
            "balanceAfterTransaction" : int(str(re.sub("\D", "", item[-1]))) / 100,
            "dateTime" : item[0].strftime("%Y-%m-%d"),
            "description" : item[2],
        }
        if i == 0:
            trans_dict["type"] : "OPENING"
        elif trans_dict["balanceAfterTransaction"] > (int(str(re.sub("\D", "", transaction_list[i-1][-1]))) / 100):
            trans_dict["type"] : "CREDIT"
        else:
            trans_dict["type"] : "DEBIT"

        result_list.append(trans_dict)

    abb = round(cumumlative / (transaction_list[-1][0] - transaction_list[0][0]).days, 2)
    print("abb:", abb)
    # print(*transactions,sep='\n')
    # print(*date_list,sep='\n')
    # print(*balance_list,sep='\n')
    # row = ''
    # f = open('text.csv', 'a', encoding="utf-8")
    # # row = "\"" + filename + "\"" + "," \
    # #       + "\"" + raw + "\"" + "\n"
    # for item in transaction_list:
    #     row = "\"" + filename + "\"" + "," \
    #       + "\"" + str(item) + "\"" + "," \
    #       + "\"" + raw + "\"" + "\n"
    #     f.write(row)
    # ## Python will convert \n to os.linesep
    # f.close()

    content = {
        'status': 'TRUE',
        'ABB': abb,
        'transactions': result_list
    }

    with open('test.json', 'a') as json_file:
        json.dump(content, json_file)
