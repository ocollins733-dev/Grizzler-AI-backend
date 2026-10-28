CREATE DATABASE IF NOT EXISTS chatbot_db;
USE chatbot_db;

CREATE TABLE IF NOT EXISTS grading_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    assignment_name VARCHAR(255) NOT NULL,
    student_submission LONGTEXT NOT NULL,
    grade INT NULL,
    progress INT DEFAULT 0,
    suggestions LONGTEXT NULL,
    ali_raw_response LONGTEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
