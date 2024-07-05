from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
import pandas as pd
import matplotlib.pyplot as plt
import io
import base64

# Use a non-GUI backend for Matplotlib
import matplotlib
matplotlib.use('Agg')

app = Flask(__name__)
app.secret_key = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///workload.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Define database models
class Staff(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    total_hours_per_week = db.Column(db.Float, nullable=False)

class Case(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.String(50), nullable=False)
    assigned_staff = db.Column(db.String(50), db.ForeignKey('staff.name'), nullable=False)
    estimated_hours = db.Column(db.Float, nullable=False)
    risk_level = db.Column(db.String(50), nullable=False)

class AdditionalWorkload(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), db.ForeignKey('staff.name'), nullable=False)
    additional_hours = db.Column(db.Float, nullable=False)

# Ensure database is created within application context
with app.app_context():
    db.create_all()

# Risk level weighting scheme
risk_weights = {'High': 3.0, 'Medium': 2.0, 'Low': 1.0}

@app.route('/')
def index():
    staff_data = Staff.query.all()
    case_data = Case.query.all()
    additional_workload_data = AdditionalWorkload.query.all()
    return render_template('index.html', 
                           staff_data=staff_data, 
                           case_data=case_data, 
                           additional_workload_data=additional_workload_data, 
                           risk_weights=risk_weights)

@app.route('/add_staff', methods=['POST'])
def add_staff():
    name = request.form['name']
    hours = float(request.form['hours'])
    new_staff = Staff(name=name, total_hours_per_week=hours)
    db.session.add(new_staff)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/delete_staff/<name>', methods=['POST'])
def delete_staff(name):
    staff = Staff.query.filter_by(name=name).first()
    db.session.delete(staff)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/add_case', methods=['POST'])
def add_case():
    case_id = request.form['case_id']
    assigned_staff = request.form['assigned_staff']
    risk_level = request.form['risk_level']
    estimated_hours = risk_weights[risk_level]
    new_case = Case(case_id=case_id, assigned_staff=assigned_staff, estimated_hours=estimated_hours, risk_level=risk_level)
    db.session.add(new_case)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/delete_case/<int:id>', methods=['POST'])
def delete_case(id):
    case = Case.query.get(id)
    db.session.delete(case)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/add_additional_workload', methods=['POST'])
def add_additional_workload():
    name = request.form['name']
    additional_hours = float(request.form['additional_hours'])
    additional_workload = AdditionalWorkload.query.filter_by(name=name).first()
    if additional_workload:
        additional_workload.additional_hours = additional_hours
    else:
        new_additional_workload = AdditionalWorkload(name=name, additional_hours=additional_hours)
        db.session.add(new_additional_workload)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/delete_additional_workload/<int:id>', methods=['POST'])
def delete_additional_workload(id):
    additional_workload = AdditionalWorkload.query.get(id)
    db.session.delete(additional_workload)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/update_weights', methods=['POST'])
def update_weights():
    global risk_weights
    risk_weights['High'] = float(request.form['high_weight'])
    risk_weights['Medium'] = float(request.form['medium_weight'])
    risk_weights['Low'] = float(request.form['low_weight'])
    return redirect(url_for('index'))

@app.route('/calculate', methods=['POST'])
def calculate():
    staff_data = Staff.query.all()
    case_data = Case.query.all()
    additional_workload_data = AdditionalWorkload.query.all()

    # Convert to DataFrames
    staff_df = pd.DataFrame([(s.name, s.total_hours_per_week) for s in staff_data], columns=['Name', 'Total Hours per Week'])
    case_df = pd.DataFrame([(c.case_id, c.assigned_staff, c.estimated_hours, c.risk_level) for c in case_data], columns=['Case ID', 'Assigned Staff', 'Estimated Hours', 'Risk Level'])
    additional_workload_df = pd.DataFrame([(a.name, a.additional_hours) for a in additional_workload_data], columns=['Name', 'Additional Hours'])

    # Apply weights to case hours directly
    case_df['Weighted Hours'] = case_df['Estimated Hours']

    # Calculate total workload for each staff
    workload_summary = case_df.groupby('Assigned Staff')['Weighted Hours'].sum().reset_index()
    workload_summary = workload_summary.merge(staff_df, left_on='Assigned Staff', right_on='Name', how='right')
    workload_summary = workload_summary.merge(additional_workload_df, on='Name', how='left')

    # Fill NaN values with 0
    workload_summary = workload_summary.fillna({'Weighted Hours': 0, 'Additional Hours': 0})

    # Calculate total assigned hours and remaining capacity
    workload_summary['Total Assigned Hours'] = workload_summary['Weighted Hours'] + workload_summary['Additional Hours']
    workload_summary['Remaining Capacity'] = workload_summary['Total Hours per Week'] - workload_summary['Total Assigned Hours']
    # Calculate workload capacity as a percentage
    workload_summary['Workload Capacity (%)'] = (workload_summary['Total Assigned Hours'] / workload_summary['Total Hours per Week']) * 100

    # Plot the results
    img = io.BytesIO()
    fig, ax = plt.subplots()
    workload_summary.plot(kind='bar', x='Name', y=['Total Assigned Hours', 'Remaining Capacity'], stacked=True, ax=ax)
    ax.set_title('Workload Summary')
    ax.set_xlabel('Staff')
    ax.set_ylabel('Hours')
    plt.savefig(img, format='png')
    img.seek(0)
    plot_url = base64.b64encode(img.getvalue()).decode()

    return render_template('workload_summary.html', tables=[workload_summary.to_html(classes='data')], plot_url=plot_url)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)

