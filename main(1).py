from centroidtracker import CentroidTracker
from trackableobject import TrackableObject
from imutils.video import FPS
import numpy as np
import argparse
import imutils
import time
import dlib
import cv2
import math
import os
import collections
# construct the argument parse
ap = argparse.ArgumentParser()
ap.add_argument("-i", "--input", required=True, help="path to input video")
ap.add_argument("-o", "--output", required=True, help="path to output video")
ap.add_argument("-y", "--yolo", required=True, help="base path to YOLO directory")
ap.add_argument("-c", "--confidence", type=float, default=0.5, help="minimum probability to filter weak detections")
ap.add_argument("-t", "--threshold", type=float, default=0.3, help="threshold when applyong non-maxima suppression")
ap.add_argument("-s", "--skip-frames", type=int, default=10, help="# of skip frames between detections")

args = vars(ap.parse_args())

# speed estimation
def estimateSpeed(location1, location2, ppm, fs):
	d_pixels = math.sqrt(math.pow(location2[0] - location1[0], 2) + math.pow(location2[1] - location1[1], 2))
	d_meters = d_pixels/ppm
	speed = d_meters*fs*3.6
	return speed

labelsPath = os.path.sep.join(['yolo.names'])
LABELS = open(labelsPath).read().strip().split("\n")

np.random.seed(42)
COLORS = np.random.randint(0, 255, size=(len(LABELS), 3), dtype="uint8")

weightsPath = os.path.sep.join(["yolov4-custom_final.weights"])
configPath = os.path.sep.join(["yolov4-custom.cfg"])

net = cv2.dnn.readNetFromDarknet(configPath, weightsPath)
ln = net.getLayerNames()
ln = [ln[i - 1] for i in net.getUnconnectedOutLayers()]

# initialize the video stream
vs = cv2.VideoCapture("test.mp4")
fs = vs.get(cv2.CAP_PROP_FPS)
writer = None
(W, H) = (None, None)

# init centroid tracker
ct = CentroidTracker(maxDisappeared=40, maxDistance=50)
trackers = []
stop_count = []
trackableOjects = {}
totalFrames = 0
fps = FPS().start()
LASER= 350
LASER_DOC = 680
count = 0
k=0
v=0
while True:
    (ret, frame) = vs.read()
    if not ret:
        break
    frame = imutils.resize(frame, width=1000)
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # if the frame dimensions are empty, set them
    if W is None or H is None:
        (H, W) = frame.shape[:2]

    # init a writer to write video to disk
    if args["output"] is not None and writer is None:
        fourcc = cv2.VideoWriter_fourcc(*"XVID")
        writer = cv2.VideoWriter(args["output"], fourcc, 30, (W, H), True)
    blob = cv2.dnn.blobFromImage(frame, 1 / 255, (416, 416), swapRB=True, crop=False)
    net.setInput(blob)
    layerOutputs = net.forward(ln)
    # init the status for detecting or tracking
    status = "Waiting"
    rects = []

    # Check to see if we should run a more detection method to aid our tracker
        # set the status and init our new set of object trackers
    status = "Detecting"
    trackers = []
    # init ourlists of detected bboxes, confidences, class IDs
    boxes = []
    confidences = []
    classIDs = []
    #T???o ???????ng line
    cv2.line(frame, (0, LASER), (LASER_DOC, LASER), (204, 90, 208), 2)
    cv2.line(frame, (LASER_DOC, 0), (LASER_DOC, 1000), (204, 90, 208), 2)

    #l???p qua t???ng layerOutputs
    for output in layerOutputs:
        # l???p qua t???ng object ???????c detect
        for detection in output:
            # extract the classID and confidence of the current object detection
            scores = detection[5:]
            classID = np.argmax(scores)
            confidence = scores[classID]

            # b??? qua c??c detect kh??ng t???t
            if confidence > args["confidence"]:
                # ????a t??? l??? bbox ph?? h???p k??ch th?????c ???nh
                # YOLO tr??? v??? gi?? tr??? center (x, y) v?? width, height
                box = detection[0:4]*np.array([W, H, W, H])
                (centerX, centerY, width, height) = box.astype("int")
                #t??nh c??c gi?? tr??? x, y l?? g??c tr??n c???a bbox
                x = int(centerX - (width/2))
                y = int(centerY - (height/2))
                # c???p nh???t bboxes, confidences, classIDs
                boxes.append([x, y, int(width), int(height)])
                confidences.append(float(confidence))
                classIDs.append(classID)

    # apply non-maxima suppresion to suppress weak
    idxs = cv2.dnn.NMSBoxes(boxes, confidences, args["confidence"], args["threshold"])

    # ?????m b???o c?? ??t nh???t 1 detection t???n t???i
    if len(idxs) > 0:
            # loop over the indexes we are keeping
        for i in idxs.flatten():
            # init rect for tracking
            startX = boxes[i][0]
            startY = boxes[i][1]
            endX = boxes[i][0] + boxes[i][2]
            endY = boxes[i][1] + boxes[i][3]
            # construct a dlib rectangle object and start dlib correlation tracker
            tracker = dlib.correlation_tracker()
            rect = dlib.rectangle(startX, startY, endX, endY)
            tracker.start_track(rgb, rect)
            color = [int(c) for c in COLORS[classIDs[i]]]
            cv2.rectangle(frame, (startX, startY), (endX, endY), color, 2)
            text = "{}: {:.4f}% ".format(LABELS[classIDs[i]], confidences[i]*100)
            cv2.putText(frame, text, (startX, startY - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
            # add the tracker to our list and we can use it during skip frames
            trackers.append(tracker)

        # loop over the trackers
        for tracker in trackers:

            # set the status
            status = "Tracking"
            # update the tracker and grab the updated position
            tracker.update(rgb)
            pos = tracker.get_position()

            # unpack the position object
            startX = int(pos.left())
            startY = int(pos.top())
            endX = int(pos.right())
            endY = int(pos.bottom())

            ppm = math.sqrt(math.pow(endX-startX, 2))
            # add the bbox coordinates to the rectangles list
            rects.append((startX, startY, endX, endY))

    # use the centroid tracker to associate the object 1 and object 2
    objects = ct.update(rects)
    # loop over the tracked objects
    speed = 0
    j = 0
    for (objectID, centroid) in objects.items():
        # init speed array
        # speed = 0
        # check to see if a tracktable object exists for the current objectID
        to = trackableOjects.get(objectID, None)

        # if there is no tracktable object, create one
        if to is None:
            to = TrackableObject(objectID, centroid)
        # otherwise, use it for speed estimation
        else:
            to.centroids.append(centroid)
            location1 = to.centroids[-2]
            location2 = to.centroids[-1]
            speed = estimateSpeed(location1, location2, ppm, fs)
        trackableOjects[objectID] = to

        cv2.putText(frame, "ID:{} {:.1f} km/h".format(objectID, speed), (centroid[0] - 10, centroid[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 2)
        cv2.circle(frame, (centroid[0], centroid[1]), 4, (0, 0, 255), -1)
        if (centroid[1] > LASER) and (centroid[0] < LASER_DOC):
            stop_count.append(objectID)
            print (stop_count)
            c = collections.Counter(stop_count)
            print(c)
            count = len(sorted([k for k, v in collections.Counter(stop_count).items() if v > 0], key=stop_count.index))
            print(count)

    cv2.putText(frame, "so phuong tien qua vach: {:03d}".format(count), (10, 30), cv2.FONT_HERSHEY_DUPLEX, 0.5, (0, 0, 0), 1)
    cv2.putText(frame, "so phuong tien da track: {:03d}".format(objectID+1), (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 255), 1)

    if writer is not None:
        writer.write(frame)

    cv2.imshow("Frame", frame)
    key = cv2.waitKey(1) & 0xFF
    if key == ord("q"):
        break
    totalFrames += 1
    fps.update()
fps.stop()
writer.release()
vs.release()

cv2.destroyAllWindows()
